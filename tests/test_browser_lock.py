"""Tests for extensible browser URL lock (utils/browser_lock.py)."""

from unittest.mock import MagicMock, patch

from notebooklm_tools.utils.browser_lock import (
    BrowserLockPolicy,
    build_host_resolver_rules,
    get_browser_lock_args,
    parse_host_list,
    resolve_browser_lock_policy,
)
from notebooklm_tools.utils.config import AuthConfig, Config


def test_parse_host_list_sanitizes_and_deduplicates() -> None:
    raw = " NotebookLM.google.com , *.gstatic.com, invalid host!, foo;bar, notebooklm.google.com "
    assert parse_host_list(raw) == ("notebooklm.google.com", "*.gstatic.com")


def test_off_mode_produces_no_rules() -> None:
    policy = BrowserLockPolicy(mode="off")
    assert build_host_resolver_rules(policy) is None
    assert get_browser_lock_args(policy) == []


def test_allowlist_mode_allows_notebook_and_auth_blocks_rest() -> None:
    policy = BrowserLockPolicy(
        mode="allowlist",
        allow_hosts=("custom-sso.example.com",),
        block_hosts=("play.google.com",),
    )
    rules = build_host_resolver_rules(policy)
    assert rules is not None
    assert rules.startswith("MAP * ~NOTFOUND, ")
    assert "EXCLUDE notebooklm.google.com" in rules
    assert "EXCLUDE notebook.google.com" in rules
    assert "EXCLUDE accounts.google.com" in rules
    assert "EXCLUDE custom-sso.example.com" in rules
    assert "EXCLUDE play.google.com" not in rules
    assert "myaccount.google.com" not in rules
    assert "mail.google.com" not in rules


def test_blocklist_mode_blocks_sensitive_google_hosts() -> None:
    policy = BrowserLockPolicy(
        mode="blocklist",
        allow_hosts=("drive.google.com",),
        block_hosts=("extra.example.com",),
    )
    rules = build_host_resolver_rules(policy)
    assert rules is not None
    assert "MAP myaccount.google.com ~NOTFOUND" in rules
    assert "MAP mail.google.com ~NOTFOUND" in rules
    assert "MAP extra.example.com ~NOTFOUND" in rules
    assert "MAP drive.google.com ~NOTFOUND" not in rules


def test_resolve_policy_prefers_env_over_config(monkeypatch) -> None:
    fake_cfg = Config(
        auth=AuthConfig(
            browser_lock_mode="blocklist",
            browser_lock_allow="cfg.example.com",
            browser_lock_block="cfgblock.example.com",
        )
    )
    monkeypatch.setenv("NLM_BROWSER_LOCK_MODE", "allowlist")
    monkeypatch.setenv("NLM_BROWSER_LOCK_ALLOW", "env.example.com")
    monkeypatch.delenv("NLM_BROWSER_LOCK_BLOCK", raising=False)

    with patch("notebooklm_tools.utils.config.load_config", return_value=fake_cfg):
        policy = resolve_browser_lock_policy()

    assert policy.mode == "allowlist"
    assert policy.allow_hosts == ("env.example.com",)
    assert policy.block_hosts == ("cfgblock.example.com",)


def test_launch_chrome_process_includes_host_resolver_rules(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NLM_BROWSER_LOCK_MODE", "allowlist")
    mock_popen = MagicMock()

    with (
        patch("notebooklm_tools.utils.cdp.get_chrome_path", return_value="/usr/bin/google-chrome"),
        patch("notebooklm_tools.utils.cdp._get_profile_dir_for_launch", return_value=tmp_path),
        patch("notebooklm_tools.utils.cdp.subprocess.Popen", mock_popen),
    ):
        from notebooklm_tools.utils.cdp import launch_chrome_process

        launch_chrome_process(port=9222, headless=False, profile_name="default")

    assert mock_popen.called
    launched_args = mock_popen.call_args[0][0]
    assert any(arg.startswith("--host-resolver-rules=MAP * ~NOTFOUND, ") for arg in launched_args)


def test_is_url_allowed_and_cdp_enforcement() -> None:
    from notebooklm_tools.utils.browser_lock import enforce_cdp_url_lock, is_url_allowed

    policy = BrowserLockPolicy(mode="allowlist")
    assert is_url_allowed("https://notebooklm.google.com/notebook/123", policy) is True
    assert is_url_allowed("https://accounts.google.com/signin", policy) is True
    assert is_url_allowed("https://ssl.gstatic.com/ui/v1/icons.png", policy) is True
    assert is_url_allowed("https://myaccount.google.com/security", policy) is False
    assert is_url_allowed("https://mail.google.com/mail/u/0/", policy) is False

    nav_calls: list[tuple[str, str]] = []
    redirected = enforce_cdp_url_lock(
        "ws://127.0.0.1:9222/page/1",
        "https://myaccount.google.com/",
        "https://notebooklm.google.com/",
        lambda ws, url: nav_calls.append((ws, url)),
        policy=policy,
    )
    assert redirected is True
    assert nav_calls == [("ws://127.0.0.1:9222/page/1", "https://notebooklm.google.com/")]


def test_chrome_policy_payload_and_export(tmp_path) -> None:
    import json

    from notebooklm_tools.utils.browser_lock import (
        build_chrome_policy_payload,
        export_chrome_policy,
    )

    allow_payload = build_chrome_policy_payload(BrowserLockPolicy(mode="allowlist"))
    assert allow_payload["URLBlocklist"] == ["*"]
    assert "notebooklm.google.com" in allow_payload["URLAllowlist"]
    assert "accounts.google.com" in allow_payload["URLAllowlist"]
    assert "myaccount.google.com" not in allow_payload["URLAllowlist"]

    out_file = export_chrome_policy(
        tmp_path / "nlm_lock.json",
        BrowserLockPolicy(mode="blocklist"),
    )
    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert "myaccount.google.com" in loaded["URLBlocklist"]
    assert "URLAllowlist" not in loaded
