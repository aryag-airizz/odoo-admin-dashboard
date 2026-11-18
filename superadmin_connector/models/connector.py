# pyrefly: ignore[missing-import]
from odoo import api, models, release
# pyrefly: ignore[missing-import]
from odoo.exceptions import AccessDenied


class SuperadminConnector(models.AbstractModel):
    _name = 'superadmin.connector'
    _description = 'Superadmin Reporting Connector'

    @api.model
    def get_health(self):
        """Return basic database health information."""

        if not self.env.user.has_group(
            'superadmin_connector.group_superadmin_connector'
        ):
            raise AccessDenied(
                'You are not authorized to access the Superadmin Connector.'
            )

        return {
            'status': 'connected',
            'database': self.env.cr.dbname,
            'company': self.env.company.name,
            'odoo_version': release.version,
        }
