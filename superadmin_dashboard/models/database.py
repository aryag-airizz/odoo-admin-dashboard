from odoo import fields, models


class SuperadminDatabase(models.Model):
    _name = 'superadmin.database'
    _description = 'Managed Odoo Database'
    _order = 'name'

    name = fields.Char(
        string='Database Name',
        required=True,
    )

    company_id = fields.Many2one(
        'superadmin.company',
        string='Company',
        required=True,
        ondelete='cascade',
    )

    url = fields.Char(
        string='Odoo URL',
        help="Base URL of the company's Odoo instance.",
    )

    environment = fields.Selection(
        [
            ('production', 'Production'),
            ('testing', 'Testing'),
            ('development', 'Development'),
        ],
        string='Environment',
        default='production',
        required=True,
    )

    notes = fields.Text(string='Notes')

    active = fields.Boolean(
        string='Active',
        default=True,
    )
