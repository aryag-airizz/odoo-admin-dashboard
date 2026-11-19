import logging
from datetime import timedelta

# pyrefly: ignore[missing-import]
from odoo import api, fields, models, release
# pyrefly: ignore[missing-import]
from odoo.exceptions import AccessError
# pyrefly: ignore[missing-import]
from odoo.http import request

_logger = logging.getLogger(__name__)

CONNECTOR_GROUP = 'superadmin_connector.group_superadmin_connector'
API_VERSION = 1
MAX_COMPANIES = 500
STATS_WINDOW_DAYS = 30


class SuperadminConnector(models.AbstractModel):
    _name = 'superadmin.connector'
    _description = 'Superadmin Reporting Connector'

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------
    def _check_connector_access(self, method):
        """Gate + audit trail. Every public method must call this first."""
        user = self.env.user
        try:
            remote = request.httprequest.remote_addr if request else 'n/a'
        except RuntimeError:  # no HTTP request (tests, shell)
            remote = 'n/a'
        if not user.has_group(CONNECTOR_GROUP):
            _logger.warning(
                "superadmin connector DENIED %s: uid=%s ip=%s", method, user.id, remote)
            raise AccessError(
                self.env._("You are not authorized to access the Superadmin Connector."))
        _logger.info("superadmin connector %s: uid=%s ip=%s", method, user.id, remote)

    def _integration_user_warnings(self):
        """Tell the hub when the key is more powerful than it needs to be."""
        user = self.env.user
        return {
            'integration_user_is_internal': not user.share,
            'integration_user_is_admin': user.has_group('base.group_system'),
        }

    # ------------------------------------------------------------------
    # Public API (called by the hub through /json/2)
    # ------------------------------------------------------------------
    @api.model
    @api.readonly
    def get_health(self):
        self._check_connector_access('get_health')
        return {
            'status': 'connected',
            'api_version': API_VERSION,
            'database': self.env.cr.dbname,
            'odoo_version': release.version,
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            'security': self._integration_user_warnings(),
        }

    @api.model
    @api.readonly
    def get_overview(self):
        """Health + every company of this database with aggregate stats."""
        self._check_connector_access('get_overview')
        # Narrow, deliberate sudo: the integration user owns no business
        # rights; the whitelist of aggregates below is the access policy.
        env = self.env(su=True)
        companies = env['res.company'].search([], limit=MAX_COMPANIES)
        stats = self._collect_stats(env, companies)
        return {
            'status': 'connected',
            'api_version': API_VERSION,
            'database': self.env.cr.dbname,
            'odoo_version': release.version,
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            'security': self._integration_user_warnings(),
            'apps': self._installed_apps(env),
            'companies': [self._company_payload(c, stats.get(c.id, {})) for c in companies],
        }

    # ------------------------------------------------------------------
    # Internals (underscore => not callable over JSON-2)
    # ------------------------------------------------------------------
    @api.model
    def _installed_apps(self, env):
        return [
            app for app, model in (
                ('sale', 'sale.order'), ('account', 'account.move'),
                ('purchase', 'purchase.order'), ('stock', 'stock.picking'),
                ('hr', 'hr.employee'),
            ) if model in env
        ]

    @api.model
    def _company_payload(self, company, stats):
        partner = company.partner_id
        return {
            'id': company.id,
            'name': company.name,
            'parent_id': company.parent_id.id or False,
            'email': company.email or False,
            'phone': company.phone or False,
            'website': company.website or False,
            'vat': company.vat or False,
            'currency': company.currency_id.name or False,
            'city': partner.city or False,
            'country': partner.country_id.name or False,
            'stats': stats,
        }

    @api.model
    def _collect_stats(self, env, companies):
        """Return {company_id: {metric: value}}; metrics of apps that are not
        installed are simply absent."""
        ids = companies.ids
        since = fields.Datetime.now() - timedelta(days=STATS_WINDOW_DAYS)
        res = {cid: {} for cid in ids}

        def fill(metric, rows):
            for company, value in rows:
                if company.id in res:
                    res[company.id][metric] = value or 0

        # Internal (non-share) active users per company
        Users = env['res.users']
        for company in companies:
            res[company.id]['users_count'] = Users.search_count([
                ('share', '=', False), ('company_ids', 'in', company.id)])

        if 'hr.employee' in env:
            fill('employees_count', env['hr.employee']._read_group(
                [('company_id', 'in', ids)], ['company_id'], ['__count']))
        if 'sale.order' in env:
            fill('sale_orders_30d', env['sale.order']._read_group(
                [('company_id', 'in', ids), ('state', '=', 'sale'),
                 ('date_order', '>=', since)], ['company_id'], ['__count']))
        if 'purchase.order' in env:
            fill('purchase_orders_30d', env['purchase.order']._read_group(
                [('company_id', 'in', ids), ('state', '=', 'purchase'),
                 ('date_order', '>=', since)], ['company_id'], ['__count']))
        if 'stock.picking' in env:
            fill('open_transfers', env['stock.picking']._read_group(
                [('company_id', 'in', ids),
                 ('state', 'in', ('confirmed', 'waiting', 'assigned'))],
                ['company_id'], ['__count']))
        if 'account.move' in env:
            Move = env['account.move']
            posted = [('company_id', 'in', ids), ('state', '=', 'posted')]
            # *_signed fields are expressed in the company currency
            fill('revenue_30d', Move._read_group(
                posted + [('move_type', 'in', ('out_invoice', 'out_refund')),
                          ('invoice_date', '>=', since.date())],
                ['company_id'], ['amount_untaxed_signed:sum']))
            fill('receivable', Move._read_group(
                posted + [('move_type', 'in', ('out_invoice', 'out_refund')),
                          ('payment_state', 'in', ('not_paid', 'partial'))],
                ['company_id'], ['amount_residual_signed:sum']))
            fill('payable', Move._read_group(
                posted + [('move_type', 'in', ('in_invoice', 'in_refund')),
                          ('payment_state', 'in', ('not_paid', 'partial'))],
                ['company_id'], ['amount_residual_signed:sum']))
        return res
