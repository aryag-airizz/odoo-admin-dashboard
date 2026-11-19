"""Outbound HTTP client of the hub: the only place that talks to a spoke.

Hardening applied here:
* only two whitelisted connector methods can ever be called;
* HTTPS enforced (HTTP only if the system parameter allows it, for dev);
* SSRF guard: private/loopback hosts rejected unless explicitly allowed,
  link-local (cloud metadata) always rejected, userinfo in URL rejected;
* TLS verification always on, redirects never followed, hard timeouts and a
  response size cap;
* error messages are short, generic and never contain the key or the body.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

import requests

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ALLOWED_METHODS = frozenset({'get_health', 'get_overview'})
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
PARAM_ALLOW_HTTP = 'superadmin_dashboard.allow_http'
PARAM_ALLOW_PRIVATE = 'superadmin_dashboard.allow_private_hosts'


class ConnectorError(UserError):
    """A safe-to-display connector failure."""


def _flag(env, key):
    return env['ir.config_parameter'].sudo().get_bool(key)


def normalize_base_url(url):
    return (url or '').strip().rstrip('/')


def validate_url(env, url):
    """Static + DNS checks. Raises ConnectorError; returns the base URL."""
    url = normalize_base_url(url)
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname:
        raise ConnectorError(env._("The URL must start with https:// and contain a host name."))
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
        raise ConnectorError(env._("Use the bare base URL only (e.g. https://erp.example.com)."))
    if parts.scheme == 'http' and not _flag(env, PARAM_ALLOW_HTTP):
        raise ConnectorError(env._("Plain HTTP is not allowed: the API key would travel unencrypted. Use HTTPS."))
    allow_private = _flag(env, PARAM_ALLOW_PRIVATE)
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ConnectorError(env._("The host name cannot be resolved."))
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise ConnectorError(env._("This address is not allowed."))
        if not allow_private and (ip.is_private or ip.is_loopback):
            raise ConnectorError(env._("Private or local addresses are not allowed."))
    return url


def call_connector(env, base_url, db_name, api_key, method):
    """POST /json/2/superadmin.connector/<method> and return the decoded JSON."""
    if method not in ALLOWED_METHODS:
        raise ConnectorError(env._("Unsupported connector method."))
    base_url = validate_url(env, base_url)
    endpoint = f"{base_url}/json/2/superadmin.connector/{method}"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'X-Odoo-Database': db_name,
        'Content-Type': 'application/json',
        'User-Agent': 'superadmin-hub/1',
    }
    try:
        resp = requests.post(endpoint, headers=headers, json={}, stream=True,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                             allow_redirects=False, verify=True)
    except requests.exceptions.SSLError:
        raise ConnectorError(env._("TLS certificate verification failed."))
    except requests.exceptions.Timeout:
        raise ConnectorError(env._("The database did not answer in time."))
    except requests.exceptions.RequestException:
        raise ConnectorError(env._("The database is unreachable."))
    try:
        status = resp.status_code
        if 300 <= status < 400:
            raise ConnectorError(env._("Redirects are refused. Check the URL (http vs https, trailing path)."))
        if status == 401:
            raise ConnectorError(env._("Authentication failed: the API key is invalid or expired."))
        if status == 403:
            raise ConnectorError(env._("Access denied: the API user is not in the Superadmin Integration group."))
        if status == 404:
            raise ConnectorError(env._("Not found: the connector module is not installed, or the database name is wrong."))
        if status != 200:
            raise ConnectorError(env._("Unexpected answer from the database (HTTP %s).", status))
        body = b''
        for chunk in resp.iter_content(65536):
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                raise ConnectorError(env._("The answer is too large and was discarded."))
        try:
            data = requests.models.complexjson.loads(body)
        except ValueError:
            raise ConnectorError(env._("The answer is not valid JSON."))
        if not isinstance(data, dict):
            raise ConnectorError(env._("Unexpected answer format."))
        return data
    finally:
        resp.close()
