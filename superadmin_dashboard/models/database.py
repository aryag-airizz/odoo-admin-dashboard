import base64
import hashlib
import logging
import os
from datetime import timedelta

# pyrefly: ignore[missing-import]
from cryptography.fernet import Fernet, InvalidToken

# pyrefly: ignore[missing-import]
from odoo import api, fields, models
# pyrefly: ignore[missing-import]
from odoo.exceptions import AccessError, UserError, ValidationError

from . import connector_client

_logger = logging.getLogger(__name__)

MANAGER = 'superadmin_dashboard.group_superadmin_manager'
SECRET_ENV = 'SUPERADMIN_SECRET_KEY'
EXPIRY_WARNING_DAYS = 7
STAT_FIELDS = (
    'users_count', 'employees_count', 'sale_orders_30d', 'purchase_orders_30d',
    'open_transfers', 'revenue_30d', 'receivable', 'payable',
)


def _fernet(env):
    secret = os.environ.get(SECRET_ENV, '')
    if len(secret) < 24:
        raise UserError(env._(
            "Encryption is not configured. Set the environment variable %s "
            "(at least 24 random characters, e.g. `openssl rand -base64 48`) "
            "on the hub server and restart Odoo.", SECRET_ENV))
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class SuperadminDatabase(models.Model):
    """A registered connection to a database that runs superadmin_connector.

    Registering does NOT create an Odoo database: it stores how to reach an
    existing one.
    """
    _name = 'superadmin.database'
    _description = 'Connected Odoo database'
    _order = 'name'

    name = fields.Char(string='Label', required=True)
    client_name = fields.Char(string='Client / Owner', help="Optional: who owns this database.")
    db_name = fields.Char(string='Database name', required=True,
                          help="Technical name, as sent in the X-Odoo-Database header.")
    url = fields.Char(string='Odoo URL', required=True,
                      help="Base URL only, e.g. https://erp.client.com")
    environment = fields.Selection(
        [('production', 'Production'), ('testing', 'Testing'), ('development', 'Development')],
        default='production', required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    # --- secret (encrypted at rest, never sent back to any client) ---
    api_key = fields.Char(
        string='API key', compute='_compute_api_key', inverse='_inverse_api_key',
        groups=MANAGER, copy=False,
        help="Write-only. Stored encrypted; it cannot be displayed again.")
    api_key_enc = fields.Text(groups=MANAGER, copy=False, prefetch=False)
    has_api_key = fields.Boolean(compute='_compute_has_api_key')
    api_key_expires_on = fields.Date(
        string='Key expires on', copy=False,
        help="Copy the expiry you chose when creating the key. The hub warns before it lapses.")
    key_expiring = fields.Boolean(compute='_compute_key_expiring', search='_search_key_expiring')

    # --- sync status ---
    state = fields.Selection(
        [('draft', 'Not synced'), ('connected', 'Connected'), ('error', 'Error')],
        default='draft', readonly=True, copy=False)
    last_sync_at = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Char(readonly=True, copy=False)
    odoo_version = fields.Char(readonly=True, copy=False)
    installed_apps = fields.Char(readonly=True, copy=False)
    privileged_key = fields.Boolean(
        string='Over-privileged API user', readonly=True, copy=False,
        help="The API user is an internal user or an administrator.")

    company_ids = fields.One2many('superadmin.company', 'database_id', string='Companies', readonly=True)
    company_count = fields.Integer(compute='_compute_company_count')

    _target_uniq = models.Constraint(
        'UNIQUE(url, db_name)', 'This database is already registered.')

    # ------------------------------------------------------------------
    # Computes / constraints
    # ------------------------------------------------------------------
    def _compute_api_key(self):
        self.api_key = False  # never reveal

    def _compute_has_api_key(self):
        for rec in self:
            rec.has_api_key = bool(rec.sudo().api_key_enc)

    @api.depends('api_key_expires_on')
    def _compute_key_expiring(self):
        limit = fields.Date.today() + timedelta(days=EXPIRY_WARNING_DAYS)
        for rec in self:
            rec.key_expiring = bool(rec.api_key_expires_on and rec.api_key_expires_on <= limit)

    def _search_key_expiring(self, operator, value):
        limit = fields.Date.today() + timedelta(days=EXPIRY_WARNING_DAYS)
        positive = (operator == '=') == bool(value)
        domain = [('api_key_expires_on', '!=', False), ('api_key_expires_on', '<=', limit)]
        return domain if positive else ['!'] + ['&'] + domain

    @api.depends('company_ids')
    def _compute_company_count(self):
        data = dict(self.env['superadmin.company']._read_group(
            [('database_id', 'in', self.ids)], ['database_id'], ['__count']))
        for rec in self:
            rec.company_count = data.get(rec, 0)

    @api.constrains('url')
    def _check_url_syntax(self):
        # Syntax/policy only (no DNS) so that saving never blocks on network.
        from urllib.parse import urlsplit
        for rec in self:
            parts = urlsplit(connector_client.normalize_base_url(rec.url))
            if parts.scheme not in ('https', 'http') or not parts.hostname \
                    or parts.username or parts.password or parts.query or parts.fragment \
                    or parts.path not in ('', '/'):
                raise ValidationError(self.env._("Use the bare base URL, e.g. https://erp.client.com"))
            if parts.scheme == 'http' and not connector_client._flag(self.env, connector_client.PARAM_ALLOW_HTTP):
                raise ValidationError(self.env._("Plain HTTP is not allowed. Use HTTPS."))

    def _inverse_api_key(self):
        self._check_manager()
        for rec in self:
            value = (rec.api_key or '').strip()
            if value:
                token = _fernet(self.env).encrypt(value.encode()).decode()
                rec.sudo().api_key_enc = token
                _logger.info("superadmin hub: API key set for database #%s by uid=%s", rec.id, self.env.uid)

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager()
        for vals in vals_list:
            if vals.get('url'):
                vals['url'] = connector_client.normalize_base_url(vals['url'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('url'):
            vals['url'] = connector_client.normalize_base_url(vals['url'])
        if {'url', 'db_name'} & set(vals):
            # Re-pointing a record must not send the old key to a new host.
            vals.update(state='draft', last_error=False)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _check_manager(self):
        if not (self.env.su or self.env.user.has_group(MANAGER)):
            raise AccessError(self.env._("Only Superadmin managers can do this."))

    def _get_api_key(self):
        """Decrypt the key. Private: never exposed over RPC."""
        self.ensure_one()
        token = self.sudo().api_key_enc
        if not token:
            raise UserError(self.env._("No API key is stored for this database."))
        try:
            return _fernet(self.env).decrypt(token.encode()).decode()
        except InvalidToken:
            raise UserError(self.env._(
                "The stored key cannot be decrypted (was %s changed?). Enter the API key again.", SECRET_ENV))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_test_connection(self):
        self._check_manager()
        self.ensure_one()
        try:
            data = connector_client.call_connector(
                self.env, self.url, self.db_name, self._get_api_key(), 'get_health')
        except UserError as e:
            raise UserError(e.args[0]) from None
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': self.env._("Connection OK"), 'type': 'success', 'sticky': False,
                'message': self.env._("Odoo %(v)s, database %(db)s.", v=data.get('odoo_version'), db=data.get('database')),
            },
        }

    def action_sync(self):
        self._check_manager()
        for rec in self:
            rec._sync_one()
        return True

    @api.model
    def action_sync_all(self):
        """Called by the dashboard button."""
        self._check_manager()
        self.search([])._sync_one_each()
        return True

    @api.model
    def _cron_sync_all(self):
        self.search([])._sync_one_each()

    def _sync_one_each(self):
        for rec in self:
            try:
                with self.env.cr.savepoint():
                    rec._sync_one()
            except Exception:  # one broken tenant must never stop the others
                _logger.exception("superadmin hub: unexpected sync failure for database #%s", rec.id)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def _sync_one(self):
        self.ensure_one()
        rec = self.sudo()
        try:
            data = connector_client.call_connector(
                self.env, rec.url, rec.db_name, rec._get_api_key(), 'get_overview')
            rec._apply_overview(data)
        except UserError as e:
            rec.write({'state': 'error', 'last_error': str(e.args[0])[:200], 'last_sync_at': fields.Datetime.now()})
            _logger.warning("superadmin hub: sync of database #%s failed: %s", rec.id, e.args[0])
            return False
        return True

    def _apply_overview(self, data):
        self.ensure_one()
        companies = data.get('companies')
        if not isinstance(companies, list):
            raise connector_client.ConnectorError(self.env._("Unexpected answer format."))
        now = fields.Datetime.now()
        existing = {c.remote_id: c for c in self.company_ids}
        seen = set()
        for item in companies:
            rid = item.get('id')
            if not isinstance(rid, int):
                continue
            seen.add(rid)
            stats = item.get('stats') or {}
            vals = {
                'name': str(item.get('name') or '')[:255] or f'#{rid}',
                'is_subsidiary': bool(item.get('parent_id')),
                'email': item.get('email') or False,
                'phone': item.get('phone') or False,
                'website': item.get('website') or False,
                'vat': item.get('vat') or False,
                'city': item.get('city') or False,
                'country': item.get('country') or False,
                'currency': item.get('currency') or False,
                'synced_at': now,
            }
            for f in STAT_FIELDS:
                vals[f] = stats.get(f) or 0
            if rid in existing:
                existing[rid].write(vals)
            else:
                self.env['superadmin.company'].create({**vals, 'database_id': self.id, 'remote_id': rid})
        # companies deleted remotely disappear locally
        stale = self.company_ids.filtered(lambda c: c.remote_id not in seen)
        stale.unlink()
        security = data.get('security') or {}
        self.write({
            'state': 'connected', 'last_error': False, 'last_sync_at': now,
            'odoo_version': data.get('odoo_version'),
            'installed_apps': ', '.join(data.get('apps') or []) or False,
            'privileged_key': bool(security.get('integration_user_is_internal')
                                   or security.get('integration_user_is_admin')),
        })
