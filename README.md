# Odoo Superadmin Dashboard (hub & spoke), Odoo 20

| Module | Install in | Purpose |
|---|---|---|
| `superadmin_connector` | **every client database** | Read-only, aggregate-only endpoint (`get_health`, `get_overview`) |
| `superadmin_dashboard` | **one central database** | Registry of databases, scheduled sync, dashboard |

## Flow
1. Client DB: install connector, create the integration user + API key.
2. Hub: *Register database* (URL, DB name, key). The key is encrypted and never shown again.
3. Hub syncs every 15 min (cron) or on **Sync all**; companies are *discovered*, never typed in.
4. The dashboard reads the hub's local mirror, so it opens instantly and survives a client outage.
   Only databases whose connector answers contribute data.

## Setup: client database (spoke)
1. Install `superadmin_connector`.
2. Create a user (e.g. `hub_integration`) that is a **Portal** user with ONLY the group
   *Superadmin Integration*. Do not make it Internal, and never an Administrator.
   The hub flags databases where this is not the case.
3. Create an API key for that user (scope `rpc`). Odoo caps this group at 30 days (`api_key_duration`).
   Portal users can create keys when *Settings > Allow API keys for portal users* is on and debug mode is active;
   alternatively generate it from `odoo shell` with `env['res.users.apikeys'].with_user(user)._generate('rpc','hub',expiry)`.
4. Test: `curl -X POST https://CLIENT/json/2/superadmin.connector/get_health -H "Authorization: Bearer KEY" -H "X-Odoo-Database: DBNAME" -H "Content-Type: application/json" -d '{}'`

## Setup: hub
1. Export a secret **before starting Odoo** (it encrypts stored keys; losing it means re-entering keys):
   `export SUPERADMIN_SECRET_KEY="$(openssl rand -base64 48)"`
2. Install `superadmin_dashboard`; give users *Superadmin Dashboard / Viewer* or *Manager*.
3. Local/dev only (System Parameters): `superadmin_dashboard.allow_http` and
   `superadmin_dashboard.allow_private_hosts` = `True`. Leave unset in production.

## Hardening checklist
- Portal-type integration user, key expiry set, rotate before the date shown on the dashboard.
- HTTPS only; reverse proxy on the client side allows `/json/2/superadmin.connector/*` from the hub IP only.
- `list_db = False`, `dbfilter` set, `proxy_mode = True` on every instance.
- Hub on its own database/server; few Managers; database access to `api_key_enc` restricted and DB backups encrypted.
- Known limit: the hostname is resolved for the SSRF check and again by the HTTP library (DNS rebinding window);
  restrict hub egress at the firewall as defence in depth.

## Tests
`odoo-bin -d test -i superadmin_connector,superadmin_dashboard --test-tags=/superadmin_connector,/superadmin_dashboard --stop-after-init`
