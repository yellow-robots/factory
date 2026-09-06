"""Unit tests for tools/notify.py — per-stakeholder changelog delivery (it-36 slice I, #474).

Derived from the mandate's Test expectations: "the manifest readers' tri-state; notify.py per
channel with fakes and the signature verified". Every network call is stubbed (`_http_post`, `_gh`)
— no real HTTP, no real gh.
"""
import hashlib
import hmac
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "notify.py"
sys.path.insert(0, str(ROOT / "tools"))
import notify  # noqa: E402


# ============ read_stakeholders: tri-state ============

def test_read_stakeholders_absent_when_no_table_declared():
    status, entries = notify.read_stakeholders('check_cmd = "true"\n')
    assert status == "absent" and entries is None


def test_read_stakeholders_absent_on_a_manifest_that_fails_to_parse():
    status, entries = notify.read_stakeholders('check_cmd = "true\nbroken = [[[')
    assert status == "absent" and entries is None


def test_read_stakeholders_ok_with_one_well_formed_entry():
    manifest = '''
[[stakeholders]]
name = "ops"
channel = "telegram"
address = "https://n8n.example/webhook/abc"
events = ["release"]
'''
    status, entries = notify.read_stakeholders(manifest)
    assert status == "ok"
    assert entries == [{"name": "ops", "channel": "telegram",
                        "address": "https://n8n.example/webhook/abc", "events": ["release"]}]


def test_read_stakeholders_ok_with_multiple_entries_and_channels():
    manifest = '''
[[stakeholders]]
name = "ops"
channel = "telegram"
address = "https://n8n.example/webhook/abc"
events = ["release"]

[[stakeholders]]
name = "docs-team"
channel = "issue-comment"
address = "yellow-robots/factory#1"
events = ["all"]

[[stakeholders]]
name = "audit-system"
channel = "webhook"
address = "https://audit.example/hook"
events = ["release"]

[[stakeholders]]
name = "watchers"
channel = "github-release"
address = "n/a"
events = ["release"]
'''
    status, entries = notify.read_stakeholders(manifest)
    assert status == "ok" and len(entries) == 4


def test_read_stakeholders_malformed_bad_channel():
    manifest = '''
[[stakeholders]]
name = "ops"
channel = "carrier-pigeon"
address = "x"
events = ["release"]
'''
    status, reason = notify.read_stakeholders(manifest)
    assert status == "malformed"
    assert "channel" in reason


def test_read_stakeholders_malformed_missing_name():
    manifest = '''
[[stakeholders]]
channel = "webhook"
address = "x"
events = ["release"]
'''
    status, reason = notify.read_stakeholders(manifest)
    assert status == "malformed" and "name" in reason


def test_read_stakeholders_malformed_empty_events():
    manifest = '''
[[stakeholders]]
name = "ops"
channel = "webhook"
address = "x"
events = []
'''
    status, reason = notify.read_stakeholders(manifest)
    assert status == "malformed" and "events" in reason


def test_read_stakeholders_malformed_not_a_list():
    status, reason = notify.read_stakeholders('stakeholders = "not-a-list"\n')
    assert status == "malformed"


# ============ B2 (cold review of #474): issue-comment address is validated at read time ===========

def test_read_stakeholders_malformed_issue_comment_address_missing_hash():
    manifest = '''
[[stakeholders]]
name = "docs"
channel = "issue-comment"
address = "yellow-robots/factory"
events = ["release"]
'''
    status, reason = notify.read_stakeholders(manifest)
    assert status == "malformed" and "owner/repo#N" in reason


def test_read_stakeholders_malformed_issue_comment_address_non_numeric_issue():
    manifest = '''
[[stakeholders]]
name = "docs"
channel = "issue-comment"
address = "yellow-robots/factory#abc"
events = ["release"]
'''
    status, reason = notify.read_stakeholders(manifest)
    assert status == "malformed" and "owner/repo#N" in reason


def test_read_stakeholders_ok_issue_comment_valid_address():
    manifest = '''
[[stakeholders]]
name = "docs"
channel = "issue-comment"
address = "yellow-robots/factory#465"
events = ["release"]
'''
    status, entries = notify.read_stakeholders(manifest)
    assert status == "ok" and len(entries) == 1


def test_split_issue_ref_parses_owner_repo_and_number():
    assert notify._split_issue_ref("yellow-robots/factory#465") == ("yellow-robots/factory", "465")


def test_split_issue_ref_rejects_malformed_forms():
    assert notify._split_issue_ref("yellow-robots/factory") is None
    assert notify._split_issue_ref("#465") is None
    assert notify._split_issue_ref("yellow-robots/factory#") is None
    assert notify._split_issue_ref("yellow-robots/factory#abc") is None


def test_wants_event_matches_named_event_or_all():
    assert notify.wants_event({"events": ["release"]}, "release") is True
    assert notify.wants_event({"events": ["release"]}, "other") is False
    assert notify.wants_event({"events": ["all"]}, "anything") is True
    assert notify.wants_event({"events": []}, "release") is False


# ============ signing ============

def test_hmac_signature_matches_a_reference_computation():
    secret = b"topsecret"
    body = b'{"a":1}'
    assert notify.hmac_signature(secret, body) == hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_hmac_signature_differs_with_a_different_secret():
    body = b"same body"
    assert notify.hmac_signature(b"secret1", body) != notify.hmac_signature(b"secret2", body)


def test_build_event_id_stable_per_release_and_stakeholder():
    a = notify.build_event_id("it/36", "ops")
    b = notify.build_event_id("it/36", "ops")
    c = notify.build_event_id("it/36", "docs-team")
    d = notify.build_event_id("it/37", "ops")
    assert a == b
    assert a != c
    assert a != d


# ============ delivery per channel, with fakes ============

TELEGRAM = {"name": "ops", "channel": "telegram", "address": "https://n8n.example/hook",
           "events": ["release"]}
WEBHOOK = {"name": "audit", "channel": "webhook", "address": "https://audit.example/hook",
          "events": ["release"]}
ISSUE_COMMENT = {"name": "docs", "channel": "issue-comment", "address": "yellow-robots/factory#1",
                 "events": ["release"]}
GITHUB_RELEASE = {"name": "watchers", "channel": "github-release", "address": "n/a",
                  "events": ["release"]}


def test_notify_telegram_posts_signed_json(monkeypatch):
    calls = []

    def fake_post(url, body, headers):
        calls.append((url, body, headers))
        return True, "HTTP 200"

    monkeypatch.setattr(notify, "_http_post", fake_post)
    ok, detail = notify.notify_stakeholder(TELEGRAM, {"iteration": "it-36", "release": "it/36",
                                                       "event_id": "abc123"}, b"sekrit")
    assert ok is True
    (url, body, headers) = calls[0]
    assert url == TELEGRAM["address"]
    assert "X-YR-Signature" in headers
    assert headers["X-YR-Signature"] == hmac.new(b"sekrit", body, hashlib.sha256).hexdigest()
    parsed = json.loads(body)
    assert parsed["event_id"] == "abc123"


def test_notify_webhook_posts_signed_json_to_its_own_address(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_http_post", lambda url, body, headers: (calls.append((url, body, headers)) or (True, "ok")))
    ok, _ = notify.notify_stakeholder(WEBHOOK, {"iteration": "it-36", "release": "it/36", "event_id": "x"}, b"s")
    assert ok is True
    assert calls[0][0] == WEBHOOK["address"]


def test_notify_webhook_delivery_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(notify, "_http_post", lambda url, body, headers: (False, "connection refused"))
    ok, detail = notify.notify_stakeholder(WEBHOOK, {"release": "it/36", "event_id": "x"}, b"s")
    assert ok is False and "connection refused" in detail


def test_notify_issue_comment_posts_via_gh(monkeypatch):
    """B2 (cold review of #474): gh rejects the combined 'owner/repo#N' form outright ('invalid
    issue format') — the argv must split into gh's own <number> --repo <owner/repo> shape, the
    same shape main() already uses for the YR-CHANGELOG post itself. Full argv asserted, not a
    membership check that a wrong shape could also satisfy."""
    calls = []

    def fake_gh(argv):
        calls.append(argv)
        return 0, "", ""

    monkeypatch.setattr(notify, "_gh", fake_gh)
    ok, detail = notify.notify_stakeholder(ISSUE_COMMENT, {"iteration": "it-36", "release": "it/36",
                                                            "notes": "shipped", "event_id": "x"}, b"s")
    assert ok is True
    argv = calls[0]
    text = notify._render_comment({"iteration": "it-36", "release": "it/36", "notes": "shipped",
                                   "event_id": "x"})
    assert argv == ["issue", "comment", "1", "--repo", "yellow-robots/factory", "--body", text]


def test_gh_seam_respects_gh_bin_env_override(monkeypatch):
    """The PM instance's own routing (design_gate.py, round_record.py, sources.py precedent):
    every `gh` call goes through $GH_BIN, so pointing it at tools/gh-app runs under the App's
    identity, never a bare `gh` login."""
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    monkeypatch.setenv("GH_BIN", "/path/to/tools/gh-app")
    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    notify._gh(["issue", "comment", "1", "--body", "x"])
    assert calls[0][0] == "/path/to/tools/gh-app"


def test_notify_issue_comment_gh_failure_is_reported(monkeypatch):
    monkeypatch.setattr(notify, "_gh", lambda argv: (1, "", "not found"))
    ok, detail = notify.notify_stakeholder(ISSUE_COMMENT, {"release": "it/36", "event_id": "x"}, b"s")
    assert ok is False and "not found" in detail


def test_notify_github_release_channel_needs_no_network_call(monkeypatch):
    """The GitHub Release IS the notification for this channel — no _http_post/_gh call at all."""
    monkeypatch.setattr(notify, "_http_post", lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")))
    monkeypatch.setattr(notify, "_gh", lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")))
    ok, detail = notify.notify_stakeholder(GITHUB_RELEASE, {"release": "it/36", "event_id": "x"}, b"s")
    assert ok is True


# ============ notify_all: filtering by event, delivered-set accuracy ============

def test_notify_all_filters_by_event_and_returns_only_delivered_names(monkeypatch):
    monkeypatch.setattr(notify, "_http_post", lambda url, body, headers: (True, "ok"))
    monkeypatch.setattr(notify, "_gh", lambda argv: (0, "", ""))
    stakeholders = [TELEGRAM, ISSUE_COMMENT, {**WEBHOOK, "events": ["other-event"]}]
    delivered = notify.notify_all(stakeholders, "release", {"iteration": "it-36", "release": "it/36"}, b"s")
    assert set(delivered) == {"ops", "docs"}


def test_notify_all_excludes_a_stakeholder_whose_delivery_failed():
    def flaky_post(url, body, headers):
        return (url == TELEGRAM["address"]), "ok" if url == TELEGRAM["address"] else "fail"

    import notify as _n
    orig = _n._http_post
    try:
        _n._http_post = flaky_post
        delivered = _n.notify_all([TELEGRAM, WEBHOOK], "release", {"release": "it/36"}, b"s")
        assert delivered == ["ops"]
    finally:
        _n._http_post = orig


def test_notify_all_assigns_a_distinct_event_id_per_stakeholder(monkeypatch):
    seen = []
    monkeypatch.setattr(notify, "_http_post", lambda url, body, headers: (seen.append(json.loads(body)["event_id"]) or (True, "ok")))
    notify.notify_all([TELEGRAM, WEBHOOK], "release", {"release": "it/36"}, b"s")
    assert len(seen) == 2 and len(set(seen)) == 2


def test_notify_all_prints_a_failed_delivery_to_stderr(monkeypatch, capsys):
    """I4 (cold review of #474): a failed channel is never silent."""
    monkeypatch.setattr(notify, "_http_post", lambda url, body, headers: (False, "connection refused"))
    delivered = notify.notify_all([WEBHOOK], "release", {"release": "it/36"}, b"s")
    assert delivered == []
    err = capsys.readouterr().err
    assert "audit (webhook): connection refused" in err


def test_notify_all_prints_nothing_to_stderr_on_success(monkeypatch, capsys):
    monkeypatch.setattr(notify, "_http_post", lambda url, body, headers: (True, "ok"))
    notify.notify_all([WEBHOOK], "release", {"release": "it/36"}, b"s")
    assert capsys.readouterr().err == ""


# ============ B3 (cold review of #474): a missing secret fails CLOSED, never open ==================

def test_network_stakeholders_want_true_for_telegram_or_webhook():
    assert notify.network_stakeholders_want([TELEGRAM], "release") is True
    assert notify.network_stakeholders_want([WEBHOOK], "release") is True


def test_network_stakeholders_want_false_for_issue_comment_or_github_release_alone():
    assert notify.network_stakeholders_want([ISSUE_COMMENT, GITHUB_RELEASE], "release") is False


def test_network_stakeholders_want_false_when_no_one_wants_the_event():
    assert notify.network_stakeholders_want([TELEGRAM], "some-other-event") is False


# ============ the record ============

def test_record_body_matches_yr_changelog_grammar():
    sys.path.insert(0, str(ROOT / "tools"))
    import records
    import check_trail

    reg = records.load()
    row = records.get(reg, "YR-CHANGELOG")
    body = notify.record_body("it-36", "it/36", ["ops", "docs"])
    assert body.startswith(row["marker"])
    assert check_trail._missing_fields(row, [body]) == []
    assert "ops,docs" in body


def test_record_body_names_none_when_nothing_delivered():
    body = notify.record_body("it-36", "it/36", [])
    assert "delivered=none" in body


# ============ CLI ============

def _manifest(tmp_path, stakeholders_toml=""):
    m = tmp_path / "factory.toml"
    m.write_text('check_cmd = "true"\n' + stakeholders_toml)
    return m


def test_cli_post_test_mode_writes_nothing_delivers_nothing(tmp_path):
    manifest = _manifest(tmp_path, '''
[[stakeholders]]
name = "ops"
channel = "telegram"
address = "https://n8n.example/hook"
events = ["release"]
''')
    out = subprocess.run([
        sys.executable, str(TOOL), "post",
        "--manifest", str(manifest), "--iteration", "it-36", "--release", "it/36",
        "--epic", "465", "--repo", "yellow-robots/factory", "--test-mode",
    ], capture_output=True, text=True, check=True)
    assert "TEST-MODE" in out.stdout
    assert "ops" in out.stdout


def test_cli_post_refuses_on_malformed_stakeholders(tmp_path):
    manifest = _manifest(tmp_path, '''
[[stakeholders]]
name = "ops"
channel = "not-a-real-channel"
address = "x"
events = ["release"]
''')
    result = subprocess.run([
        sys.executable, str(TOOL), "post",
        "--manifest", str(manifest), "--iteration", "it-36", "--release", "it/36",
        "--epic", "465", "--repo", "yellow-robots/factory", "--test-mode",
    ], capture_output=True, text=True)
    assert result.returncode == 1
    assert "stakeholders_invalid" in result.stdout


def test_cli_post_refuses_with_secret_missing_when_a_network_stakeholder_wants_delivery(tmp_path, monkeypatch):
    """B3: an unset YR_NOTIFY_SECRET with a telegram/webhook stakeholder wanting this event fails
    CLOSED — nothing sent, even outside --test-mode (no real network call is reachable: the CLI
    refuses before ever attempting one)."""
    manifest = _manifest(tmp_path, '''
[[stakeholders]]
name = "ops"
channel = "telegram"
address = "https://n8n.example/hook"
events = ["release"]
''')
    monkeypatch.delenv("YR_NOTIFY_SECRET", raising=False)
    env = {**os.environ}
    env.pop("YR_NOTIFY_SECRET", None)
    result = subprocess.run([
        sys.executable, str(TOOL), "post",
        "--manifest", str(manifest), "--iteration", "it-36", "--release", "it/36",
        "--epic", "465", "--repo", "yellow-robots/factory",
    ], capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert "secret_missing" in result.stdout
    assert "YR_NOTIFY_SECRET" in result.stdout


def test_cli_post_issue_comment_only_needs_no_secret(tmp_path, monkeypatch):
    """The secret_missing gate is scoped to NETWORK channels only — an issue-comment-only roster
    proceeds without YR_NOTIFY_SECRET (test-mode: no real gh call is made either way)."""
    manifest = _manifest(tmp_path, '''
[[stakeholders]]
name = "docs"
channel = "issue-comment"
address = "yellow-robots/factory#1"
events = ["release"]
''')
    monkeypatch.delenv("YR_NOTIFY_SECRET", raising=False)
    result = subprocess.run([
        sys.executable, str(TOOL), "post",
        "--manifest", str(manifest), "--iteration", "it-36", "--release", "it/36",
        "--epic", "465", "--repo", "yellow-robots/factory", "--test-mode",
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert "secret_missing" not in result.stdout


def test_cli_post_never_prints_the_secret(monkeypatch, tmp_path):
    manifest = _manifest(tmp_path)
    monkeypatch.setenv("YR_NOTIFY_SECRET", "supersecretvalue")
    out = subprocess.run([
        sys.executable, str(TOOL), "post",
        "--manifest", str(manifest), "--iteration", "it-36", "--release", "it/36",
        "--epic", "465", "--repo", "yellow-robots/factory", "--test-mode",
    ], capture_output=True, text=True, env={**os.environ, "YR_NOTIFY_SECRET": "supersecretvalue"})
    assert "supersecretvalue" not in out.stdout
    assert "supersecretvalue" not in out.stderr
