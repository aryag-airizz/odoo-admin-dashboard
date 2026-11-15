from odoo import api, models


class SuperadminDashboard(models.AbstractModel):
    _name = 'superadmin.dashboard'
    _description = 'Superadmin Dashboard'

    @api.model
    def get_dashboard_data(self):
        Company = self.env['superadmin.company']
        Database = self.env['superadmin.database']

        return {
            'total_companies': Company.search_count([]),
            'active_companies': Company.search_count([
                ('active', '=', True)
            ]),
            'total_databases': Database.search_count([]),
            'production_databases': Database.search_count([
                ('environment', '=', 'production')
            ]),
        }
