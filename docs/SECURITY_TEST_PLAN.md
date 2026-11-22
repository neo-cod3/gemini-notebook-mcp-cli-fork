# Live Security Test Plan

This document outlines a step-by-step live security verification plan for `gemini-notebook-mcp-cli-fork`, covering browser URL isolation (`browser_lock`), encrypted credential storage (`protected` mode), CLI/MCP safety boundaries, and session revocation.

> **Important:** Never print, log, or commit decrypted cookies, `credentials.enc` contents, or raw OS keystore values.

---

## 1. Prerequisites

Run all commands from the repository root using the local `.venv`:

```bash
uv run nlm --help
```

Use an isolated test profile (for example, `sec-test`) so your primary profile is untouched.

---

## 2. Browser URL Lock (`allowlist` & `blocklist`)

### 2.1 Enable strict `allowlist` mode

```bash
uv run nlm config set auth.browser_lock_mode allowlist
```

### 2.2 Positive test: Sign-in and NotebookLM access

```bash
uv run nlm login --profile sec-test --storage protected
```

**Expected:**
- Google sign-in (`accounts.google.com`, including 2FA/Passkey) loads normally.
- After authentication, `https://notebooklm.google.com/` or `https://notebook.google.com/` loads and `nlm login` completes.

### 2.3 Negative test: Blocked Google services and external URLs

While the auth browser window is open (or using `--clear-profile` on a fresh run), attempt to navigate to or click links for:
- `https://myaccount.google.com/` (Google Account settings)
- `https://mail.google.com/` (Gmail)
- `https://drive.google.com/` (Google Drive)
- `https://example.com/` (arbitrary external site)

**Expected:**
- Chromium blocks DNS resolution via `--host-resolver-rules` (`ERR_NAME_NOT_RESOLVED`), and
- CDP polling (`enforce_cdp_url_lock`) redirects any disallowed URL back to NotebookLM.

### 2.4 Extensibility test: Environment variable overrides

```bash
NLM_BROWSER_LOCK_MODE=blocklist uv run nlm login --profile sec-test
```

**Expected:**
- External sites (e.g., `https://example.com/`) load, while sensitive Google hosts (`myaccount.google.com`, `mail.google.com`, `drive.google.com`, etc.) remain blocked.
- Custom additions via `NLM_BROWSER_LOCK_ALLOW` / `NLM_BROWSER_LOCK_BLOCK` (or `auth.browser_lock_allow` / `auth.browser_lock_block`) take effect without code changes.

### 2.5 Chrome Enterprise Policy JSON export (optional)

Verify that the policy generator produces a valid `URLBlocklist` / `URLAllowlist` JSON file:

```bash
uv run python -c "from notebooklm_tools.utils.browser_lock import export_chrome_policy, BrowserLockPolicy; print(export_chrome_policy('/tmp/nlm_chrome_policy.json', BrowserLockPolicy(mode='allowlist')))"
```

---

## 3. Encrypted Credential Storage (`protected` mode)

### 3.1 Verify storage mode

```bash
uv run nlm auth storage status
```

**Expected:**
- Active storage mode is `protected`.

### 3.2 Verify on-disk files (redacted check)

```bash
ls -la ~/.notebooklm-mcp-cli/profiles/sec-test/
```

**Expected:**
- `credentials.enc` and `metadata.json` exist.
- Plaintext `cookies.json` does **not** exist in the profile directory.

---

## 4. CLI & MCP Safety Boundaries

### 4.1 Read operations & diagnostics

```bash
uv run nlm doctor
uv run nlm notebook list --profile sec-test
```

**Expected:**
- Commands succeed and no raw cookies, CSRF tokens, or keystore secrets appear in stdout/logs.

### 4.2 Confirmation gates on destructive MCP tools

When running the MCP server (`uv run notebooklm-mcp`), verify that destructive tools (`notebook_delete`, `source_delete`, `studio_delete`, `note_delete`, `chat_delete`) reject execution unless `confirm=True` is explicitly passed.

---

## 5. Session Revocation Drill

1. In your primary browser, open your Google Account → **Security → Your devices**.
2. Locate the separate Chrome session created by `nlm login` and click **Sign out**.
3. Run:
   ```bash
   uv run nlm notebook list --profile sec-test
   ```

**Expected:**
- The revoked session immediately loses API access (or requires re-authentication), while your primary browser and phone remain signed in.

---

## 6. Automated Unit Verification

Run the automated unit tests for `browser_lock` and layering boundaries:

```bash
uv run pytest tests/test_browser_lock.py tests/test_layering.py -v
```
