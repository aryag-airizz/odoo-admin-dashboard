
{
    'name': 'Superadmin Dashboard',
    'version': '1.0.0',
    'summary': 'Centralized management of multiple companies and Odoo databases',
    'description': """
        Central Superadmin Dashboard
        Manage multiple companies, Odoo databases,
        company administrators and integrations.
    """,
    'category': 'Administration',
    'author': 'Internal',
    'license': 'LGPL-3',

    'depends': [
        'base',
        'web',
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/company_views.xml',
        'views/database_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'superadmin_dashboard/static/src/js/dashboard.js',
            'superadmin_dashboard/static/src/xml/dashboard.xml',
            'superadmin_dashboard/static/src/scss/dashboard.scss',
        ],
    },

    'application': True,
    'installable': True,
    'auto_install': False,
}
