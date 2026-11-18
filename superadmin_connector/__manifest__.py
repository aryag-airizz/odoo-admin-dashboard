{
    'name': 'Superadmin Connector',
    'version': '20.0.1.0.0',
    'category': 'Administration',
    'summary': 'Secure reporting integration for Superadmin Dashboard',
    'description': """
        Superadmin Connector
        ====================

        Provides authenticated, read-only reporting integration
        for centrally managed Odoo databases.

        Features:
        - Company information
        - User and employee statistics
        - Customer and contact statistics
        - Sales reporting
        - Accounting summaries
        - Purchase and inventory summaries
        - Database connectivity monitoring
    """,
    'author': 'AIRIZZ',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
    ],
    'data': [
    'security/security.xml',
],
    'installable': True,
    'application': False,
    'auto_install': False,
}
