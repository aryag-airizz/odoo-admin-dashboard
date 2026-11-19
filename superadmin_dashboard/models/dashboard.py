from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

VIEWER = 'superadmin_dashboard.group_superadmin_dashboard'
MANAGER = 'superadmin_dashboard.group_superadmin_manager'
STALE_AFTER = timedelta(minutes=45)  # three missed 15-minute syncs
MAX_COMPANY_ROWS = 500


class SuperadminDashboard(models.AbstractModel):
    _name = 'superadmin.dashboard'
    _description = 'Superadmin Dashboard'

    @api.model
    def get_dashboard_data(self):
        user = self.env.user
        if not user.has_group(VIEWER):
            raise AccessError(self.env._("You are not allowed to open the Superadmin Dashboard."))
        # Read through the user's own rights, never the whole DB as sudo.
        Database = self.env['superadmin.database']
        Company = self.env['superadmin.company']
        databases = Database.search([])
        connected = databases.filtered(lambda d: d.state == 'connected')
        companies = Company.search([('database_id', 'in', connected.ids)], limit=MAX_COMPANY_ROWS)
        now = fields.Datetime.now()

        money = defaultdict(lambda: {'revenue_30d': 0.0, 'receivable': 0.0, 'payable': 0.0})
        for c in companies:
            bucket = money[c.currency or '—']
            bucket['revenue_30d'] += c.revenue_30d
            bucket['receivable'] += c.receivable
            bucket['payable'] += c.payable

        db_rows = []
        for d in databases:
            stale = bool(d.last_sync_at and now - d.last_sync_at > STALE_AFTER)
            db_rows.append({
                'id': d.id, 'name': d.name, 'client_name': d.client_name or '',
                'environment': d.environment, 'url': d.url, 'state': d.state,
                'last_sync_at': fields.Datetime.to_string(d.last_sync_at) if d.last_sync_at else False,
                'stale': stale, 'last_error': d.last_error or '',
                'odoo_version': d.odoo_version or '', 'apps': d.installed_apps or '',
                'company_count': d.company_count, 'key_expiring': d.key_expiring,
                'privileged_key': d.privileged_key,
            })
        last_syncs = [d.last_sync_at for d in connected if d.last_sync_at]
        return {
            'can_manage': user.has_group(MANAGER),
            'kpis': {
                'databases_total': len(databases),
                'databases_connected': len(connected),
                'databases_error': len(databases.filtered(lambda d: d.state == 'error')),
                'databases_pending': len(databases.filtered(lambda d: d.state == 'draft')),
                'companies': len(companies),
                'users': sum(companies.mapped('users_count')),
                'keys_expiring': len(databases.filtered('key_expiring')),
                'privileged_keys': len(databases.filtered('privileged_key')),
            },
            'money': [{'currency': cur, **vals} for cur, vals in sorted(money.items())],
            'databases': db_rows,
            'companies': [{
                'id': c.id, 'name': c.name, 'database': c.database_id.name,
                'database_id': c.database_id.id, 'country': c.country or '',
                'currency': c.currency or '', 'users_count': c.users_count,
                'revenue_30d': c.revenue_30d, 'receivable': c.receivable,
            } for c in companies],
            'last_sync_at': fields.Datetime.to_string(max(last_syncs)) if last_syncs else False,
        }
