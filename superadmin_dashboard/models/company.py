from odoo import fields, models


class SuperadminCompany(models.Model):
    """Read-only mirror of a res.company discovered in a connected database.

    Rows are created/updated/removed exclusively by the sync (sudo); the UI
    and ACLs only allow reading them.
    """
    _name = 'superadmin.company'
    _description = 'Company discovered in a connected database'
    _order = 'database_id, name'

    database_id = fields.Many2one(
        'superadmin.database', string='Database', required=True,
        ondelete='cascade', index=True, readonly=True)
    remote_id = fields.Integer(string='Remote ID', required=True, readonly=True)
    name = fields.Char(string='Company', required=True, readonly=True)
    is_subsidiary = fields.Boolean(readonly=True)
    email = fields.Char(readonly=True)
    phone = fields.Char(readonly=True)
    website = fields.Char(readonly=True)
    vat = fields.Char(string='Tax ID', readonly=True)
    city = fields.Char(readonly=True)
    country = fields.Char(readonly=True)
    currency = fields.Char(readonly=True)

    users_count = fields.Integer(string='Users', readonly=True)
    employees_count = fields.Integer(string='Employees', readonly=True)
    sale_orders_30d = fields.Integer(string='Sales orders (30d)', readonly=True)
    purchase_orders_30d = fields.Integer(string='Purchase orders (30d)', readonly=True)
    open_transfers = fields.Integer(string='Open transfers', readonly=True)
    revenue_30d = fields.Float(string='Revenue (30d)', readonly=True)
    receivable = fields.Float(string='Receivable', readonly=True)
    payable = fields.Float(string='Payable', readonly=True)

    database_state = fields.Selection(related='database_id.state', store=True)
    environment = fields.Selection(related='database_id.environment', store=True)
    synced_at = fields.Datetime(string='Last sync', readonly=True)

    _remote_uniq = models.Constraint(
        'UNIQUE(database_id, remote_id)',
        'A company can only be mirrored once per database.',
    )
