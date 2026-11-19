import os
import socket
from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.superadmin_dashboard.models import connector_client as cc

CALL = 'odoo.addons.superadmin_dashboard.models.database.connector_client.call_connector'
SECRET = {'SUPERADMIN_SECRET_KEY': 'x' * 40}


def public_dns(host, port, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))]


def overview(companies=None, **security):
    return {
        'status': 'connected', 'api_version': 1, 'database': 'client',
        'odoo_version': '20.0', 'apps': ['sale', 'account'],
        'security': {'integration_user_is_internal': False, 'integration_user_is_admin': False, **security},
        'companies': companies if companies is not None else [
            {'id': 1, 'name': 'Alpha', 'parent_id': False, 'currency': 'USD', 'country': 'US',
             'stats': {'users_count': 4, 'revenue_30d': 1000.0, 'receivable': 250.0}},
            {'id': 2, 'name': 'Beta', 'parent_id': 1, 'currency': 'EUR', 'country': 'FR',
             'stats': {'users_count': 2, 'revenue_30d': 500.0}},
        ],
    }


@tagged('post_install', '-at_install')
class TestHub(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, 'sa_mgr', groups='superadmin_dashboard.group_superadmin_manager')
        cls.viewer = new_test_user(cls.env, 'sa_view', groups='superadmin_dashboard.group_superadmin_dashboard')
        cls.other = new_test_user(cls.env, 'sa_other', groups='base.group_user')
        cls._env_patch = patch.dict(os.environ, SECRET)
        cls._env_patch.start()
        cls.addClassCleanup(cls._env_patch.stop)
        cls.db = cls.env['superadmin.database'].with_user(cls.manager).create({
            'name': 'Client A', 'db_name': 'client', 'url': 'https://erp.example.com',
            'api_key': 'SECRET-KEY-123456',
        })

    # ----- secret handling -------------------------------------------------
    def test_key_encrypted_and_never_returned(self):
        raw = self.env['superadmin.database'].browse(self.db.id).sudo().api_key_enc
        self.assertTrue(raw)
        self.assertNotIn('SECRET-KEY-123456', raw)
        self.assertEqual(self.db.sudo()._get_api_key(), 'SECRET-KEY-123456')
        self.assertFalse(self.db.with_user(self.manager).api_key)  # write-only
        self.assertTrue(self.db.with_user(self.manager).has_api_key)

    def test_viewer_cannot_read_key_material(self):
        rec = self.db.with_user(self.viewer)
        with self.assertRaises(AccessError):
            rec.read(['api_key_enc'])
        with self.assertRaises(AccessError):
            rec.read(['api_key'])
        self.assertTrue(rec.read(['name', 'state']))  # but can see the rest

    def test_missing_secret_refuses_to_store(self):
        with patch.dict(os.environ, {'SUPERADMIN_SECRET_KEY': ''}):
            with self.assertRaises(UserError):
                self.env['superadmin.database'].with_user(self.manager).create({
                    'name': 'X', 'db_name': 'x', 'url': 'https://x.example.com', 'api_key': 'k'})

    def test_changing_target_resets_state_and_requires_new_trust(self):
        self.db.sudo().state = 'connected'
        self.db.with_user(self.manager).write({'url': 'https://other.example.com'})
        self.assertEqual(self.db.state, 'draft')

    # ----- permissions -----------------------------------------------------
    def test_viewer_is_read_only(self):
        Db = self.env['superadmin.database'].with_user(self.viewer)
        with self.assertRaises(AccessError):
            Db.create({'name': 'n', 'db_name': 'n', 'url': 'https://n.example.com'})
        with self.assertRaises(AccessError):
            self.db.with_user(self.viewer).write({'name': 'hack'})
        with self.assertRaises(AccessError):
            self.db.with_user(self.viewer).action_sync()
        with self.assertRaises(AccessError):
            Db.action_sync_all()
        with self.assertRaises(AccessError):
            self.env['superadmin.company'].with_user(self.viewer).create(
                {'database_id': self.db.id, 'remote_id': 1, 'name': 'x'})

    def test_non_member_cannot_open_dashboard_or_data(self):
        with self.assertRaises(AccessError):
            self.env['superadmin.dashboard'].with_user(self.other).get_dashboard_data()
        with self.assertRaises(AccessError):
            self.env['superadmin.database'].with_user(self.other).search([])

    # ----- sync ------------------------------------------------------------
    def test_sync_mirrors_companies(self):
        with patch(CALL, return_value=overview()):
            self.db.with_user(self.manager).action_sync()
        self.assertEqual(self.db.state, 'connected')
        self.assertEqual(self.db.company_count, 2)
        self.assertEqual(self.db.installed_apps, 'sale, account')
        self.assertFalse(self.db.privileged_key)
        beta = self.db.company_ids.filtered(lambda c: c.remote_id == 2)
        self.assertTrue(beta.is_subsidiary)
        self.assertEqual(beta.revenue_30d, 500.0)
        # company removed remotely disappears, existing one updated, no duplicates
        data = overview([{'id': 1, 'name': 'Alpha 2', 'stats': {'users_count': 9}}])
        with patch(CALL, return_value=data):
            self.db.with_user(self.manager).action_sync()
        self.assertEqual(self.db.company_ids.mapped('name'), ['Alpha 2'])
        self.assertEqual(self.db.company_ids.users_count, 9)

    def test_sync_failure_is_recorded_without_leaking(self):
        with patch(CALL, side_effect=cc.ConnectorError('Authentication failed')):
            self.db.with_user(self.manager).action_sync()
        self.assertEqual(self.db.state, 'error')
        self.assertIn('Authentication failed', self.db.last_error)
        self.assertNotIn('SECRET-KEY', self.db.last_error)

    def test_privileged_key_is_flagged(self):
        with patch(CALL, return_value=overview(integration_user_is_internal=True)):
            self.db.with_user(self.manager).action_sync()
        self.assertTrue(self.db.privileged_key)

    def test_cron_isolates_failures(self):
        second = self.env['superadmin.database'].with_user(self.manager).create({
            'name': 'B', 'db_name': 'b', 'url': 'https://b.example.com', 'api_key': 'kb'})
        def fake(env, url, db_name, key, method):
            if db_name == 'client':
                raise RuntimeError('boom')
            return overview([{'id': 7, 'name': 'Only B'}])
        with patch(CALL, side_effect=fake):
            self.env['superadmin.database']._cron_sync_all()
        self.assertEqual(second.state, 'connected')

    # ----- dashboard -------------------------------------------------------
    def test_dashboard_only_shows_connected_data_grouped_by_currency(self):
        broken = self.env['superadmin.database'].with_user(self.manager).create({
            'name': 'Broken', 'db_name': 'br', 'url': 'https://br.example.com', 'api_key': 'k'})
        with patch(CALL, return_value=overview()):
            self.db.with_user(self.manager).action_sync()
        with patch(CALL, side_effect=cc.ConnectorError('Not found')):
            broken.with_user(self.manager).action_sync()
        data = self.env['superadmin.dashboard'].with_user(self.viewer).get_dashboard_data()
        self.assertFalse(data['can_manage'])
        self.assertEqual(data['kpis']['databases_total'], 2)
        self.assertEqual(data['kpis']['databases_connected'], 1)
        self.assertEqual(data['kpis']['databases_error'], 1)
        self.assertEqual(data['kpis']['companies'], 2)
        self.assertEqual({m['currency'] for m in data['money']}, {'USD', 'EUR'})
        self.assertNotIn('api_key', str(data))
        self.assertTrue(self.env['superadmin.dashboard'].with_user(self.manager).get_dashboard_data()['can_manage'])

    # ----- URL / SSRF policy ----------------------------------------------
    def test_url_policy(self):
        env = self.env
        with patch('socket.getaddrinfo', public_dns):
            self.assertEqual(cc.validate_url(env, 'https://erp.example.com/'), 'https://erp.example.com')
            for bad in ('ftp://x.com', 'https://u:p@x.com', 'https://x.com/web?a=1', 'https://x.com/path', 'javascript:1', ''):
                with self.assertRaises(UserError, msg=bad):
                    cc.validate_url(env, bad)
            with self.assertRaises(UserError):
                cc.validate_url(env, 'http://erp.example.com')  # plain http
        def host(ip):
            return lambda h, p, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, p))]
        with patch('socket.getaddrinfo', host('127.0.0.1')):
            with self.assertRaises(UserError):
                cc.validate_url(env, 'https://localhost')
        with patch('socket.getaddrinfo', host('10.0.0.5')):
            with self.assertRaises(UserError):
                cc.validate_url(env, 'https://intranet.example.com')
        # dev toggle allows private/loopback...
        env['ir.config_parameter'].sudo().set_bool(cc.PARAM_ALLOW_PRIVATE, True)
        with patch('socket.getaddrinfo', host('10.0.0.5')):
            self.assertTrue(cc.validate_url(env, 'https://intranet.example.com'))
        # ...but never the cloud metadata address
        with patch('socket.getaddrinfo', host('169.254.169.254')):
            with self.assertRaises(UserError):
                cc.validate_url(env, 'https://metadata.example.com')

    def test_constraint_rejects_bad_url_on_save(self):
        with self.assertRaises(ValidationError):
            self.env['superadmin.database'].with_user(self.manager).create({
                'name': 'x', 'db_name': 'x', 'url': 'http://plain.example.com'})

    # ----- HTTP client behaviour ------------------------------------------
    def _resp(self, status=200, body=b'{"a": 1}'):
        r = MagicMock(status_code=status)
        r.iter_content.return_value = [body]
        return r

    def test_http_client(self):
        env = self.env
        with patch('socket.getaddrinfo', public_dns):
            with patch('requests.post', return_value=self._resp()) as post:
                self.assertEqual(cc.call_connector(env, 'https://e.example.com', 'db', 'KEY', 'get_health'), {'a': 1})
                kw = post.call_args.kwargs
                self.assertFalse(kw['allow_redirects'])
                self.assertTrue(kw['verify'])
                self.assertEqual(kw['headers']['Authorization'], 'Bearer KEY')
                self.assertEqual(post.call_args.args[0], 'https://e.example.com/json/2/superadmin.connector/get_health')
            for status in (302, 401, 403, 404, 500):
                with patch('requests.post', return_value=self._resp(status)):
                    with self.assertRaises(cc.ConnectorError) as ctx:
                        cc.call_connector(env, 'https://e.example.com', 'db', 'KEY', 'get_health')
                    self.assertNotIn('KEY', str(ctx.exception))
            with patch('requests.post', return_value=self._resp(200, b'x' * (cc.MAX_RESPONSE_BYTES + 1))):
                with self.assertRaises(cc.ConnectorError):
                    cc.call_connector(env, 'https://e.example.com', 'db', 'KEY', 'get_overview')
            with patch('requests.post', return_value=self._resp(200, b'not json')):
                with self.assertRaises(cc.ConnectorError):
                    cc.call_connector(env, 'https://e.example.com', 'db', 'KEY', 'get_overview')

    def test_only_whitelisted_methods(self):
        with self.assertRaises(cc.ConnectorError):
            cc.call_connector(self.env, 'https://e.example.com', 'db', 'KEY', 'search_read')
