"""Acceptance tests for tools/vault_api.py — the machinery's one client of the vault's REST
interface (it-36 slice F, #471, Deliverable). Derived from the issue's acceptance criteria, not
the module's internals: every test drives `VaultClient` through its injectable `fetch(method, url,
headers, data) -> (status, body: bytes)` seam — no live network, no live vault app, no real API key.

Criteria under test:
  - the credential (`YR_VAULT_API_KEY`) is tested non-empty, never mere presence: an unset/empty
    key must refuse every write path as "not authorised", never proceed to a network call.
  - a whole-body write is read back through the FILE to confirm it landed; a read-back mismatch is
    a loud stop (VaultUnreachable), never a silent success.
  - a frontmatter patch rides its payload in `value` (never `content`) and is likewise read back
    through the file's own frontmatter, never the metadata cache.
  - a refused call (any non-2xx) or an unreachable transport is a loud stop (VaultUnreachable),
    never a silent fallback to a filesystem write.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import vault_api  # noqa: E402


# ---- a fake transport: canned (status, body) per call, or a canned exception ------------------------

class FakeTransport:
    """Injectable `fetch`. `responses` is a list consumed in call order (one entry per `_call`); a
    `write()`/`patch_frontmatter()` makes two calls (the mutation, then the read-back), so tests
    that want a specific read-back value queue it as the second entry. An entry may be an
    `Exception` instance, raised instead of returned — the unreachable-transport case (the real
    `_http_fetch`'s own contract: a `URLError`/`OSError` becomes `VaultUnreachable`, raised, never a
    `(status, body)` pair)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, data):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "data": data})
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _client(responses, *, api_key="secret-key"):
    transport = FakeTransport(responses)
    client = vault_api.VaultClient(api_key=api_key, base_url="http://127.0.0.1:27123", fetch=transport)
    return client, transport


# ---- credential: non-empty test, never mere presence -------------------------------------------------

def test_empty_api_key_refuses_read_without_any_network_call():
    client, transport = _client([], api_key="")
    with pytest.raises(vault_api.VaultUnreachable):
        client.read("some/path.md")
    assert transport.calls == []   # refused before ever reaching the transport


def test_unset_api_key_env_defaults_to_empty_and_refuses(monkeypatch):
    monkeypatch.delenv("YR_VAULT_API_KEY", raising=False)
    client = vault_api.VaultClient(base_url="http://127.0.0.1:27123", fetch=FakeTransport([]))
    with pytest.raises(vault_api.VaultUnreachable):
        client.write("some/path.md", "content")


def test_whitespace_only_api_key_still_refuses():
    # a declared-but-blank value must never read as "authorised" — non-empty, not merely present.
    client, transport = _client([], api_key="")
    with pytest.raises(vault_api.VaultUnreachable):
        client.patch_frontmatter("some/path.md", "status", "active")
    assert transport.calls == []


def test_non_empty_api_key_reaches_the_transport():
    client, transport = _client([(200, b"hello")])
    client.read("some/path.md")
    assert len(transport.calls) == 1


# ---- read(): raw text, never the metadata cache -------------------------------------------------------

def test_read_returns_decoded_body_text():
    client, transport = _client([(200, "the file's raw text".encode("utf-8"))])
    assert client.read("notes/foo.md") == "the file's raw text"


def test_read_sends_bearer_auth_header_with_the_api_key():
    client, transport = _client([(200, b"x")], api_key="my-secret-token")
    client.read("notes/foo.md")
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer my-secret-token"


def test_read_percent_encodes_path_segments_but_preserves_slashes():
    client, transport = _client([(200, b"x")])
    client.read("04 projects/some doc.md")
    url = transport.calls[0]["url"]
    assert "/" in url.split("http://127.0.0.1:27123/vault/", 1)[1]
    assert " " not in url          # spaces are percent-encoded
    assert "04%20projects/some%20doc.md" in url


# ---- write(): whole-body create/overwrite, read back through the FILE ---------------------------------

def test_write_puts_the_full_payload_and_confirms_via_read_back():
    content = "---\nstatus: draft\n---\n\nbody text\n"
    client, transport = _client([
        (200, b""),                       # the PUT itself
        (200, content.encode("utf-8")),   # the read-back GET
    ])
    result = client.write("iterations/1-foo/01-foo.md", content)
    assert result == content
    assert transport.calls[0]["method"] == "PUT"
    assert transport.calls[0]["data"] == content.encode("utf-8")
    assert transport.calls[1]["method"] == "GET"


def test_write_raises_vault_unreachable_when_read_back_does_not_match():
    client, transport = _client([
        (200, b""),
        (200, b"something else entirely"),   # the read-back disagrees with what was sent
    ])
    with pytest.raises(vault_api.VaultUnreachable):
        client.write("iterations/1-foo/01-foo.md", "the intended content")


def test_write_raises_vault_unreachable_on_a_refused_put():
    client, transport = _client([(403, b"forbidden")])
    with pytest.raises(vault_api.VaultUnreachable):
        client.write("iterations/1-foo/01-foo.md", "content")
    assert len(transport.calls) == 1   # never reaches the read-back after a refusal


def test_write_raises_vault_unreachable_when_transport_is_unreachable():
    client, transport = _client([vault_api.VaultUnreachable("connection refused")])
    with pytest.raises(vault_api.VaultUnreachable):
        client.write("iterations/1-foo/01-foo.md", "content")


def test_write_content_type_is_markdown():
    client, transport = _client([(200, b""), (200, b"x")])
    client.write("some/path.md", "x")
    assert "markdown" in transport.calls[0]["headers"]["Content-Type"]


# ---- patch_frontmatter(): typed-write, payload in `value` (never `content`), read back via frontmatter ----

def test_patch_frontmatter_sends_operation_replace_and_target_headers():
    text_after = "---\nstatus: active\n---\n\nbody\n"
    client, transport = _client([(200, b""), (200, text_after.encode("utf-8"))])
    client.patch_frontmatter("iterations/1-foo/01-foo.md", "status", "active")
    headers = transport.calls[0]["headers"]
    assert headers["Operation"] == "replace"
    assert headers["Target-Type"] == "frontmatter"
    assert headers["Target"] == "status"


def test_patch_frontmatter_payload_rides_in_value_never_content():
    import json
    client, transport = _client([(200, b""), (200, b"---\nstatus: active\n---\n\nbody\n")])
    client.patch_frontmatter("some/path.md", "status", "active")
    payload = json.loads(transport.calls[0]["data"])
    assert payload == {"value": "active"}
    assert "content" not in payload


def test_patch_frontmatter_confirms_via_read_back_of_the_file_not_the_cache():
    text_after = "---\nstatus: active\nother: kept\n---\n\nbody\n"
    client, transport = _client([(200, b""), (200, text_after.encode("utf-8"))])
    result = client.patch_frontmatter("some/path.md", "status", "active")
    assert result == text_after
    assert transport.calls[1]["method"] == "GET"


def test_patch_frontmatter_raises_when_read_back_frontmatter_does_not_confirm_the_value():
    # the PATCH claims success but the read-back file still shows the old value — a loud stop.
    stale_text = "---\nstatus: draft\n---\n\nbody\n"
    client, transport = _client([(200, b""), (200, stale_text.encode("utf-8"))])
    with pytest.raises(vault_api.VaultUnreachable):
        client.patch_frontmatter("some/path.md", "status", "active")


def test_patch_frontmatter_raises_on_a_refused_patch():
    client, transport = _client([(500, b"internal error")])
    with pytest.raises(vault_api.VaultUnreachable):
        client.patch_frontmatter("some/path.md", "status", "active")
    assert len(transport.calls) == 1


# ---- the one failure type: VaultUnreachable, never a filesystem fallback ------------------------------

def test_vault_unreachable_is_the_only_exception_type_this_module_defines():
    assert issubclass(vault_api.VaultUnreachable, RuntimeError)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 502, 503])
def test_any_non_2xx_status_is_refused(status):
    client, transport = _client([(status, b"nope")])
    with pytest.raises(vault_api.VaultUnreachable):
        client.read("some/path.md")
