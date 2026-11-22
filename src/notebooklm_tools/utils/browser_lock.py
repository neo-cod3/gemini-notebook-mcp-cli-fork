"""Extensible browser URL lock for CDP authentication launches.

Isolates the authentication browser session so users can restrict navigation
to NotebookLM and essential Google sign-in endpoints, blocking access to
account settings (myaccount.google.com), Gmail, Drive, YouTube, etc.

This module is intentionally kept separate from ``cdp.py`` so fork updates
against upstream remain minimal and conflict-free.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)

BrowserLockMode = Literal["off", "allowlist", "blocklist"]

VALID_LOCK_MODES: frozenset[str] = frozenset({"off", "allowlist", "blocklist"})

# NotebookLM / Gemini Notebook application hosts
DEFAULT_NOTEBOOK_HOSTS: tuple[str, ...] = (
    "notebooklm.google.com",
    "notebook.google.com",
    "notebooklm.cloud.google.com",
    "notebook.cloud.google.com",
    "vertexaisearch.cloud.google.com",
)

# Minimum Google auth / static asset hosts required for sign-in & 2FA flows
DEFAULT_AUTH_ESSENTIAL_HOSTS: tuple[str, ...] = (
    "accounts.google.com",
    "accounts.youtube.com",
    "*.gstatic.com",
    "*.googleapis.com",
    "*.googleusercontent.com",
    "ogs.google.com",
    "play.google.com",
    "csp.withgoogle.com",
    "127.0.0.1",
    "localhost",
)

# Sensitive Google account & app hosts blocked in "blocklist" mode
# (and excluded from "allowlist" even if added implicitly)
DEFAULT_BLOCKED_HOSTS: tuple[str, ...] = (
    "myaccount.google.com",
    "mail.google.com",
    "drive.google.com",
    "docs.google.com",
    "sheets.google.com",
    "slides.google.com",
    "calendar.google.com",
    "contacts.google.com",
    "photos.google.com",
    "takeout.google.com",
    "pay.google.com",
    "payments.google.com",
    "passwords.google.com",
    "admin.google.com",
    "console.cloud.google.com",
    "www.youtube.com",
    "youtube.com",
)

_HOST_PATTERN = re.compile(r"^(\*\.)?[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)*$")


@dataclass(frozen=True)
class BrowserLockPolicy:
    """Resolved URL restriction policy for browser launches."""

    mode: BrowserLockMode = "off"
    allow_hosts: tuple[str, ...] = ()
    block_hosts: tuple[str, ...] = ()


def _sanitize_host(host: str) -> str | None:
    """Normalize and validate a hostname or wildcard pattern for Chromium rules."""
    cleaned = host.strip().lower()
    if not cleaned:
        return None
    if cleaned in {"localhost", "127.0.0.1"}:
        return cleaned
    if _HOST_PATTERN.match(cleaned):
        return cleaned
    _logger.warning("Ignoring invalid browser_lock host pattern: %r", host)
    return None


def parse_host_list(raw: str) -> tuple[str, ...]:
    """Parse a comma-separated host list into validated, deduplicated entries."""
    if not raw:
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for item in raw.split(","):
        cleaned = _sanitize_host(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return tuple(result)


def resolve_browser_lock_policy() -> BrowserLockPolicy:
    """Resolve the active browser lock policy from env vars or config.toml.

    Environment variables override ``config.toml``:
    - ``NLM_BROWSER_LOCK_MODE``: ``off`` (default), ``allowlist``, or ``blocklist``
    - ``NLM_BROWSER_LOCK_ALLOW``: comma-separated extra allowed hosts
    - ``NLM_BROWSER_LOCK_BLOCK``: comma-separated extra blocked hosts
    """
    cfg_mode = "off"
    cfg_allow = ""
    cfg_block = ""
    try:
        from notebooklm_tools.utils.config import load_config

        auth_cfg = load_config().auth
        cfg_mode = getattr(auth_cfg, "browser_lock_mode", "off") or "off"
        cfg_allow = getattr(auth_cfg, "browser_lock_allow", "") or ""
        cfg_block = getattr(auth_cfg, "browser_lock_block", "") or ""
    except Exception:
        pass

    raw_mode = (os.environ.get("NLM_BROWSER_LOCK_MODE") or cfg_mode).strip().lower()
    if raw_mode not in VALID_LOCK_MODES:
        _logger.warning("Unknown browser_lock_mode %r, falling back to 'off'", raw_mode)
        mode: BrowserLockMode = "off"
    else:
        mode = raw_mode  # type: ignore[assignment]

    env_allow = os.environ.get("NLM_BROWSER_LOCK_ALLOW")
    env_block = os.environ.get("NLM_BROWSER_LOCK_BLOCK")

    allow_hosts = parse_host_list(env_allow if env_allow is not None else cfg_allow)
    block_hosts = parse_host_list(env_block if env_block is not None else cfg_block)

    return BrowserLockPolicy(mode=mode, allow_hosts=allow_hosts, block_hosts=block_hosts)


def build_host_resolver_rules(policy: BrowserLockPolicy) -> str | None:
    """Build Chromium ``--host-resolver-rules`` value for the given policy."""
    if policy.mode == "off":
        return None

    if policy.mode == "allowlist":
        blocked_set = set(policy.block_hosts)
        allowed: list[str] = []
        seen: set[str] = set()
        for host in (*DEFAULT_NOTEBOOK_HOSTS, *DEFAULT_AUTH_ESSENTIAL_HOSTS, *policy.allow_hosts):
            if host in blocked_set or host in seen:
                continue
            seen.add(host)
            allowed.append(host)
        excludes = ", ".join(f"EXCLUDE {host}" for host in allowed)
        return f"MAP * ~NOTFOUND, {excludes}" if excludes else "MAP * ~NOTFOUND"

    # policy.mode == "blocklist"
    allowed_set = set(policy.allow_hosts)
    blocked: list[str] = []
    seen = set()
    for host in (*DEFAULT_BLOCKED_HOSTS, *policy.block_hosts):
        if host in allowed_set or host in seen:
            continue
        seen.add(host)
        blocked.append(host)
    if not blocked:
        return None
    return ", ".join(f"MAP {host} ~NOTFOUND" for host in blocked)


def get_browser_lock_args(policy: BrowserLockPolicy | None = None) -> list[str]:
    """Return extra Chromium CLI flags enforcing the configured URL lock."""
    resolved = policy if policy is not None else resolve_browser_lock_policy()
    rules = build_host_resolver_rules(resolved)
    if not rules:
        return []
    _logger.info("Applying browser URL lock (mode=%s)", resolved.mode)
    return [f"--host-resolver-rules={rules}"]


def _host_matches(hostname: str, pattern: str) -> bool:
    """Match an exact hostname or ``*.domain`` wildcard pattern."""
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname == suffix or hostname.endswith(f".{suffix}")
    return hostname == pattern


def is_url_allowed(url: str, policy: BrowserLockPolicy | None = None) -> bool:
    """Return True if ``url`` is permitted under the active browser lock policy."""
    resolved = policy if policy is not None else resolve_browser_lock_policy()
    if resolved.mode == "off":
        return True

    if not url:
        return True
    parsed = urlparse(url)
    if parsed.scheme in {"about", "chrome", "chrome-error", "data", ""}:
        return True
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return True

    if resolved.mode == "allowlist":
        for blocked in (*DEFAULT_BLOCKED_HOSTS, *resolved.block_hosts):
            if _host_matches(hostname, blocked):
                return False
        for allowed in (*DEFAULT_NOTEBOOK_HOSTS, *DEFAULT_AUTH_ESSENTIAL_HOSTS, *resolved.allow_hosts):
            if _host_matches(hostname, allowed):
                return True
        return False

    # policy.mode == "blocklist"
    for allowed in resolved.allow_hosts:
        if _host_matches(hostname, allowed):
            return True
    for blocked in (*DEFAULT_BLOCKED_HOSTS, *resolved.block_hosts):
        if _host_matches(hostname, blocked):
            return False
    return True


def enforce_cdp_url_lock(
    ws_url: str,
    current_url: str,
    fallback_url: str,
    navigate_fn: Callable[[str, str], Any],
    policy: BrowserLockPolicy | None = None,
) -> bool:
    """Redirect away from disallowed URLs during CDP login polling.

    Returns True if navigation was blocked and redirected, False otherwise.
    """
    if is_url_allowed(current_url, policy=policy):
        return False
    _logger.warning("Blocked navigation to restricted URL during auth: %s", current_url)
    navigate_fn(ws_url, fallback_url)
    return True


def build_chrome_policy_payload(policy: BrowserLockPolicy | None = None) -> dict[str, list[str]]:
    """Build a Chrome Enterprise Policy JSON payload (URLBlocklist / URLAllowlist)."""
    resolved = policy if policy is not None else resolve_browser_lock_policy()
    if resolved.mode == "off":
        return {}

    if resolved.mode == "allowlist":
        blocked_set = set(resolved.block_hosts)
        allowlist = [
            host
            for host in dict.fromkeys(
                (*DEFAULT_NOTEBOOK_HOSTS, *DEFAULT_AUTH_ESSENTIAL_HOSTS, *resolved.allow_hosts)
            )
            if host not in blocked_set
        ]
        return {
            "URLBlocklist": ["*"],
            "URLAllowlist": allowlist,
        }

    allowed_set = set(resolved.allow_hosts)
    blocklist = [
        host
        for host in dict.fromkeys((*DEFAULT_BLOCKED_HOSTS, *resolved.block_hosts))
        if host not in allowed_set
    ]
    return {"URLBlocklist": blocklist} if blocklist else {}


def export_chrome_policy(
    output_path: str | Path,
    policy: BrowserLockPolicy | None = None,
) -> Path:
    """Write the generated Chrome policy JSON to ``output_path``."""
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_chrome_policy_payload(policy)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target
