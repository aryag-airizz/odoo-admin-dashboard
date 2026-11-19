from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

GROUP = 'superadmin_connector.group_superadmin_connector'


@tagged('post_install', '-at_install')
class TestSuperadminConnector(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Recommended setup: portal user + connector group, nothing else.
        cls.integration_user = new_test_user(
            cls.env, 'sa_conn_portal', groups=f'base.group_portal,{GROUP}')
        cls.internal_integration = new_test_user(
            cls.env, 'sa_conn_internal', groups=f'base.group_user,{GROUP}')
        cls.normal_user = new_test_user(cls.env, 'sa_conn_normal', groups='base.group_user')
        cls.portal_user = new_test_user(cls.env, 'sa_conn_portal_no', groups='base.group_portal')

    def connector(self, user):
        return self.env['superadmin.connector'].with_user(user)

    def test_health(self):
        res = self.connector(self.integration_user).get_health()
        self.assertEqual(res['status'], 'connected')
        self.assertEqual(res['database'], self.env.cr.dbname)
        self.assertEqual(res['api_version'], 1)
        self.assertTrue(res['odoo_version'].startswith('20.0'))
        self.assertFalse(res['security']['integration_user_is_internal'])
        self.assertFalse(res['security']['integration_user_is_admin'])

    def test_denied_without_group(self):
        for user in (self.normal_user, self.portal_user):
            for method in ('get_health', 'get_overview'):
                with self.assertRaises(AccessError):
                    getattr(self.connector(user), method)()

    def test_internal_integration_user_is_flagged(self):
        res = self.connector(self.internal_integration).get_health()
        self.assertTrue(res['security']['integration_user_is_internal'])

    def test_overview_lists_all_companies(self):
        second = self.env['res.company'].create({'name': 'Second Co'})
        res = self.connector(self.integration_user).get_overview()
        names = {c['name'] for c in res['companies']}
        self.assertIn('Second Co', names)
        self.assertIn(self.env.company.name, names)
        company = next(c for c in res['companies'] if c['id'] == second.id)
        self.assertIn('users_count', company['stats'])
        self.assertTrue(set(res['apps']) <= {'sale', 'account', 'purchase', 'stock', 'hr'})

    def test_overview_has_no_personal_data(self):
        res = self.connector(self.integration_user).get_overview()
        blob = str(res)
        for user in (self.normal_user, self.internal_integration):
            self.assertNotIn(user.login, blob)
            self.assertNotIn(user.name, blob)

    def test_methods_are_readonly(self):
        Model = self.env['superadmin.connector']
        self.assertTrue(type(Model).get_health._readonly)
        self.assertTrue(type(Model).get_overview._readonly)

    def test_integration_user_sees_nothing_else(self):
        """A stolen key must not be able to enumerate users or partners."""
        users = self.env['res.users'].with_user(self.integration_user).search([])
        self.assertEqual(users, self.integration_user)
        partners = self.env['res.partner'].with_user(self.integration_user).search([])
        self.assertEqual(partners, self.integration_user.partner_id)
