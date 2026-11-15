from odoo import fields, models


class SuperadminCompany(models.Model):
    _name = 'superadmin.company'
    _description = 'Managed Company'
    _order = 'name'

    name = fields.Char(
        string='Company Name',
        required=True,
    )

    code = fields.Char(
        string='Company Code',
        required=True,
        copy=False,
    )

    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    website = fields.Char(string='Website')
    notes = fields.Text(string='Notes')

    database_ids = fields.One2many(
        'superadmin.database',
        'company_id',
        string='Databases',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )
