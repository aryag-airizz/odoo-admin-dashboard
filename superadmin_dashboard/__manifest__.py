{
    'name': 'Superadmin Dashboard',
    'version': '20.0.1.0.0',
    'summary': 'Central, read-only view of every connected Odoo database and its companies',
    'description': """
Central Superadmin Dashboard (hub)
==================================

Install this module in ONE central database. Install ``superadmin_connector``
in every client database you want to monitor.

* Register a database (URL + database name + the connector user's API key).
* The hub pulls an aggregate overview through the connector (JSON-2) on a
  schedule or on demand and stores it locally.
* Companies are discovered automatically from each database: they are never
  created by hand in the hub.
* The dashboard only shows data of databases whose connector answered.
    """,
    'category': 'Administration',
    'author': 'AIRIZZ',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/cron.xml',
        'views/database_views.xml',
        'views/company_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'superadmin_dashboard/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
