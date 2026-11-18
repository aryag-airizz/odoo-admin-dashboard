
# pyrefly: ignore[missing-import]
from odoo import api, models, release

# pyrefly: ignore[missing-import]
from odoo.exceptions import AccessDenied


class SuperadminConnector(models.AbstractModel):
    _name = 'superadmin.connector'
    _description = 'Superadmin Reporting Connector'

    def _check_connector_access(self):
        """Ensure the current user belongs to the integration group."""

        if not self.env.user.has_group(
            'superadmin_connector.group_superadmin_connector'
        ):
            raise AccessDenied(
                'You are not authorized to access the Superadmin Connector.'
            )

    @api.model
    def get_health(self):
        """Return basic database health information."""

        self._check_connector_access()

        return {
            'status': 'connected',
            'database': self.env.cr.dbname,
            'company': self.env.company.name,
            'odoo_version': release.version,
        }

    @api.model
    def get_company_info(self):
        """Return information about the current company."""

        self._check_connector_access()

        company = self.env.company
        partner = company.partner_id

        return {
            'company': {
                'id': company.id,
                'name': company.name,
                'email': company.email or False,
                'phone': company.phone or False,
                'website': company.website or False,
                'vat': company.vat or False,
                'currency': {
                    'id': company.currency_id.id,
                    'name': company.currency_id.name,
                    'symbol': company.currency_id.symbol,
                },
                'address': {
                    'street': partner.street or False,
                    'street2': partner.street2 or False,
                    'city': partner.city or False,
                    'zip': partner.zip or False,
                    'state': partner.state_id.name or False,
                    'country': partner.country_id.name or False,
                },
            }
        }
