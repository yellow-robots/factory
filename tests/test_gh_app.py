"""Acceptance tests for tools/gh-app — the on-demand GitHub App installation-token wrapper behind
`GH_BIN` (it-36 slice E, #470): mint, cache, re-mint under five minutes to expiry, and the final exec
into the real `gh` under the minted identity. No live network, no live App credential — every external
(the HTTP mint call, `openssl`, `os.execvpe`) is injected or monkeypatched.

`tools/gh-app` carries no `.py` suffix (it execs as `$GH_BIN` directly), so it is loaded here via
`importlib.util.spec_from_file_location` rather than a normal import.
"""
import base64
import datetime
import importlib.machinery
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GH_APP_PATH = ROOT / "tools" / "gh-app"


def _load_gh_app():
    # `tools/gh-app` carries no `.py` suffix, so `spec_from_file_location` cannot infer a loader from
    # the extension alone — an explicit `SourceFileLoader` is required.
    loader = importlib.machinery.SourceFileLoader("gh_app_under_test", str(GH_APP_PATH))
    spec = importlib.util.spec_from_file_location("gh_app_under_test", GH_APP_PATH, loader=loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gh_app = _load_gh_app()

OPENSSL = "openssl"
pytestmark = pytest.mark.skipif(
    subprocess.run(["which", OPENSSL], capture_output=True).returncode != 0,
    reason="openssl not available on this host — the RS256 signer's one named carve-out")


def _b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.fixture(scope="module")
def rsa_keypair(tmp_path_factory):
    d = tmp_path_factory.mktemp("gh-app-rsa")
    priv, pub = d / "key.pem", d / "key.pub"
    subprocess.run([OPENSSL, "genrsa", "-out", str(priv), "2048"], check=True, capture_output=True)
    subprocess.run([OPENSSL, "rsa", "-in", str(priv), "-pubout", "-out", str(pub)],
                    check=True, capture_output=True)
    return priv, pub


def _openssl_verify(pub, data, signature):
    d = pub.parent
    datafile, sigfile = d / "verify-data.bin", d / "verify-sig.bin"
    datafile.write_bytes(data)
    sigfile.write_bytes(signature)
    result = subprocess.run(
        [OPENSSL, "dgst", "-sha256", "-verify", str(pub), "-signature", str(sigfile), str(datafile)],
        capture_output=True, text=True)
    return result.returncode == 0 and "Verified OK" in result.stdout


# ---- sign_rs256 / mint_jwt: the stdlib-only convention's one named carve-out ---------------------------

def test_sign_rs256_produces_a_signature_the_public_key_verifies(rsa_keypair, tmp_path):
    priv, pub = rsa_keypair
    data = b"the exact bytes gh-app signs"
    sig = gh_app.sign_rs256(data, str(priv))
    assert _openssl_verify(pub, data, sig)


def test_sign_rs256_raises_loudly_on_a_bad_key_path(tmp_path):
    with pytest.raises(RuntimeError, match="openssl signing failed"):
        gh_app.sign_rs256(b"data", str(tmp_path / "no-such-key.pem"))


def test_mint_jwt_header_and_payload_shape(rsa_keypair):
    priv, _ = rsa_keypair
    now = 1_800_000_000.0
    token = gh_app.mint_jwt("app-id-123", str(priv), now=now)
    header_b64, payload_b64, _sig_b64 = token.split(".")
    header = json.loads(_b64url_decode(header_b64))
    payload = json.loads(_b64url_decode(payload_b64))
    assert header == {"alg": "RS256", "typ": "JWT"}
    assert payload["iss"] == "app-id-123"
    assert payload["iat"] == int(now) - 60          # a minute of clock-skew tolerance
    assert payload["exp"] == int(now) + 9 * 60       # 9 minutes ahead — under GitHub's 10-minute JWT ceiling
    assert (payload["exp"] - payload["iat"]) <= 600  # iat 60s in the past + exp 9m ahead = the 10-minute ceiling


def test_mint_jwt_signature_verifies_against_the_public_key(rsa_keypair):
    priv, pub = rsa_keypair
    token = gh_app.mint_jwt("app-id-123", str(priv))
    signing_input, sig_b64 = token.rsplit(".", 1)
    sig = _b64url_decode(sig_b64)
    assert _openssl_verify(pub, signing_input.encode("ascii"), sig)


# ---- mint_installation_token: the injectable HTTP seam -------------------------------------------------

def test_mint_installation_token_success(rsa_keypair):
    priv, _ = rsa_keypair
    calls = []

    def fake_fetch(url, headers):
        calls.append((url, headers))
        body = json.dumps({"token": "ghs_abc123", "expires_at": "2026-09-06T13:00:00Z"}).encode()
        return 201, body

    result = gh_app.mint_installation_token(
        app_id="1", key_path=str(priv), installation="99",
        api_base="https://api.example.test", fetch=fake_fetch)
    assert result == {"token": "ghs_abc123", "expires_at": "2026-09-06T13:00:00Z"}
    assert len(calls) == 1
    url, headers = calls[0]
    assert url == "https://api.example.test/app/installations/99/access_tokens"
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Accept"] == "application/vnd.github+json"


def test_mint_installation_token_non_201_raises(rsa_keypair):
    priv, _ = rsa_keypair

    def fake_fetch(url, headers):
        return 401, b'{"message":"Bad credentials"}'

    with pytest.raises(RuntimeError, match="mint installation token failed"):
        gh_app.mint_installation_token(app_id="1", key_path=str(priv), installation="99", fetch=fake_fetch)


def test_mint_installation_token_requires_every_identity_field(rsa_keypair):
    priv, _ = rsa_keypair
    with pytest.raises(RuntimeError, match="YR_GH_APP_ID"):
        gh_app.mint_installation_token(app_id="", key_path=str(priv), installation="99",
                                        fetch=lambda *a: (201, b"{}"))
    with pytest.raises(RuntimeError, match="YR_GH_APP_ID"):
        gh_app.mint_installation_token(app_id="1", key_path="", installation="99",
                                        fetch=lambda *a: (201, b"{}"))
    with pytest.raises(RuntimeError, match="YR_GH_APP_ID"):
        gh_app.mint_installation_token(app_id="1", key_path=str(priv), installation="",
                                        fetch=lambda *a: (201, b"{}"))


# ---- the on-disk cache: round-trip, corruption-tolerant, 600 permissions --------------------------------

def test_save_and_load_cached_token_roundtrip(tmp_path):
    cache = tmp_path / "cache.json"
    gh_app.save_cached_token("tok-1", 12345.0, cache_path=str(cache))
    token, expires = gh_app.load_cached_token(cache_path=str(cache))
    assert token == "tok-1" and expires == 12345.0


def test_save_cached_token_is_not_world_or_group_readable(tmp_path):
    cache = tmp_path / "cache.json"
    gh_app.save_cached_token("tok", 1.0, cache_path=str(cache))
    assert (cache.stat().st_mode & 0o777) == 0o600


def test_load_cached_token_missing_file_degrades_to_none(tmp_path):
    token, expires = gh_app.load_cached_token(cache_path=str(tmp_path / "does-not-exist.json"))
    assert token is None and expires == 0.0


def test_load_cached_token_corrupt_file_degrades_to_none(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("not { valid json")
    token, expires = gh_app.load_cached_token(cache_path=str(cache))
    assert token is None and expires == 0.0


def test_parse_expires_at_reads_githubs_own_utc_format():
    ts = gh_app._parse_expires_at("2026-09-06T12:34:56Z")
    expected = datetime.datetime(2026, 9, 6, 12, 34, 56, tzinfo=datetime.timezone.utc).timestamp()
    assert ts == expected


# ---- get_token: cache / re-mint-under-five-minutes / mint-fresh, the acceptance criterion itself --------

def test_get_token_returns_the_cached_token_when_comfortably_before_expiry(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    now = 1_000_000.0
    gh_app.save_cached_token("cached-tok", now + 3600, cache_path=str(cache))   # an hour to go

    def must_not_mint(**kw):
        raise AssertionError("mint_installation_token must not be called against a fresh cache")

    monkeypatch.setattr(gh_app, "mint_installation_token", must_not_mint)
    token = gh_app.get_token(now=now, cache_path=str(cache))
    assert token == "cached-tok"


def test_get_token_remints_when_fewer_than_five_minutes_remain(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    now = 1_000_000.0
    gh_app.save_cached_token("stale-tok", now + 200, cache_path=str(cache))   # 200s < the 300s margin
    calls = []

    def fake_mint(**kw):
        calls.append(kw)
        return {"token": "fresh-tok", "expires_at": "2026-09-06T13:00:00Z"}

    monkeypatch.setattr(gh_app, "mint_installation_token", fake_mint)
    token = gh_app.get_token(now=now, cache_path=str(cache))
    assert token == "fresh-tok"
    assert len(calls) == 1
    cached_tok, _ = gh_app.load_cached_token(cache_path=str(cache))
    assert cached_tok == "fresh-tok"                      # the re-mint is also cached


def test_get_token_at_exactly_the_five_minute_margin_still_remints(tmp_path, monkeypatch):
    """`> EXPIRY_MARGIN_SECONDS` is the cache-hit condition — exactly the margin must re-mint, never
    treat "==" as "comfortably fresh" (a build outliving the token by even one tick must never see a
    just-expired credential)."""
    cache = tmp_path / "cache.json"
    now = 1_000_000.0
    gh_app.save_cached_token("boundary-tok", now + gh_app.EXPIRY_MARGIN_SECONDS, cache_path=str(cache))
    calls = []
    monkeypatch.setattr(gh_app, "mint_installation_token",
                         lambda **kw: (calls.append(1), {"token": "remint", "expires_at":
                                                          "2026-09-06T13:00:00Z"})[1])
    token = gh_app.get_token(now=now, cache_path=str(cache))
    assert calls == [1]
    assert token == "remint"


def test_get_token_mints_fresh_when_no_cache_exists(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    monkeypatch.setattr(gh_app, "mint_installation_token",
                         lambda **kw: {"token": "brand-new", "expires_at": "2026-09-06T13:00:00Z"})
    token = gh_app.get_token(now=1_000_000.0, cache_path=str(cache))
    assert token == "brand-new"


# ---- main(): mint/reuse, then exec the real `gh` under the minted identity ------------------------------

def test_main_execs_the_real_gh_with_the_minted_token(monkeypatch):
    monkeypatch.setattr(gh_app, "get_token", lambda **kw: "minted-tok-xyz")
    monkeypatch.setenv("GITHUB_TOKEN", "a-stale-user-token")
    calls = []

    def fake_execvpe(file, args, env):
        calls.append((file, args, env))

    monkeypatch.setattr(gh_app.os, "execvpe", fake_execvpe)
    gh_app.main(["issue", "list", "--repo", "o/r"])
    assert len(calls) == 1
    file, args, env = calls[0]
    assert file == gh_app.REAL_GH_BIN
    assert args == [gh_app.REAL_GH_BIN, "issue", "list", "--repo", "o/r"]
    assert env["GH_TOKEN"] == "minted-tok-xyz"
    assert "GITHUB_TOKEN" not in env                       # never let a stale user token outrank the App identity


def test_main_never_reads_gh_bin_itself_to_avoid_self_exec(monkeypatch):
    """`GH_BIN` is what a caller points AT this wrapper; the wrapper execs its OWN `YR_GH_APP_GH_BIN`
    (default `gh`), never `GH_BIN` — reading `GH_BIN` here would exec itself again."""
    monkeypatch.setattr(gh_app, "get_token", lambda **kw: "tok")
    monkeypatch.setenv("GH_BIN", "/path/to/this/very/wrapper")
    calls = []
    monkeypatch.setattr(gh_app.os, "execvpe", lambda file, args, env: calls.append(file))
    gh_app.main(["pr", "view", "1"])
    assert calls == [gh_app.REAL_GH_BIN]
    assert calls[0] != "/path/to/this/very/wrapper"


def test_main_mint_failure_is_loud_on_stderr_and_returns_1(monkeypatch, capsys):
    def boom(**kw):
        raise RuntimeError("gh-app: mint installation token failed (500): b'boom'")

    monkeypatch.setattr(gh_app, "get_token", boom)
    rc = gh_app.main(["issue", "list"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "gh-app:" in captured.err
    assert "mint installation token failed" in captured.err
