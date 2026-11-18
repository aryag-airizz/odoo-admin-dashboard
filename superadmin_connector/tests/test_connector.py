from odoo.exceptions import AccessDenied
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestSuperadminConnector(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.connector_group = cls.env.ref(
            'superadmin_connector.group_superadmin_connector'
        )

        cls.integration_user = new_test_user(
            cls.env,
            'superadmin_connector_test_user',
            groups='base.group_user,superadmin_connector.group_superadmin_connector',
        )

        cls.normal_user = new_test_user(
            cls.env,
            'superadmin_connector_normal_user',
            groups='base.group_user',
        )

    def test_authorized_user_can_get_health(self):
        result = self.env['superadmin.connector'].with_user(
            self.integration_user
        ).get_health()

        self.assertEqual(result['status'], 'connected')
        self.assertEqual(result['database'], self.env.cr.dbname)
        self.assertTrue(result['company'])
        self.assertTrue(result['odoo_version'].startswith('20.0'))

    def test_unauthorized_user_is_denied(self):
        with self.assertRaises(AccessDenied):
            self.env['superadmin.connector'].with_user(
                self.normal_user
            ).get_health()
