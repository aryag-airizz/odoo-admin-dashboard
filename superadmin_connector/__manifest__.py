{
    'name': 'Superadmin Connector',
    'version': '20.0.1.1.0',
    'category': 'Administration',
    'summary': 'Read-only, aggregate-only reporting endpoint for the Superadmin Dashboard',
    'description': """
Superadmin Connector
====================

Install this module in every client database that the central Superadmin
Dashboard should monitor.

It exposes two whitelisted, read-only methods over Odoo's JSON-2 API:

* ``superadmin.connector.get_health``
* ``superadmin.connector.get_overview`` (every company of the database, with
  aggregate statistics only: no customer, employee or user personal data)

Security model
--------------
* Access is restricted to the "Superadmin Integration" group.
* The integration user should be a *portal* (non-internal) user that belongs
  to that group and to nothing else. It then has no rights on business data;
  all reads are performed inside the whitelisted methods only.
* Every method is ``@api.readonly`` (executed on a read-only cursor).
* Every call is written to the server log (user, method, remote IP).
    """,
    'author': 'AIRIZZ',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': ['security/security.xml'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
