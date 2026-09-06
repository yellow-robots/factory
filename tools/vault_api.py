#!/usr/bin/env python3
"""vault_api.py — the machinery's one client of the vault's REST interface (it-36 slice F).

The plugin (obsidian-local-rest-api) serves plaintext HTTP on `127.0.0.1:27123` only (`27124` is its
conventional HTTPS port, off on this vault); its served `/openapi.yaml` is the authority over the
wire contract, never memory (skills/factory/references/documentation-model.md's own "Editing safely"
pin, :250-261). A human session speaks to the vault through the app's MCP tools; a cold machinery
process has no MCP registration, so this is its own equivalent path over the SAME underlying REST
surface — read, whole-body write, and a frontmatter-key patch — never a direct filesystem mutation
(the vault is "live + synced": app-mediated writes only).

Credential: `YR_VAULT_API_KEY`, tested non-empty (never mere presence) — unset or empty means *not
authorised to write by this path*, the fail-closed rule documentation-model.md states verbatim.
`VaultUnreachable` is the one failure type this module raises: a refused write (any non-2xx), an
unreachable app, or a write whose read-back does not confirm what was sent — a loud stop every time,
never a retry into a filesystem write (the app-down rule; the vault has no version history to
recover a corrupted block from).

Stdlib only (`urllib.request`), matching every other `tools/*.py` module. Every network call runs
through an injectable `fetch(method, url, headers, data) -> (status, body: bytes)` seam (the same
shape `tools/gh-app`'s own `_http_post` establishes) so the whole client is unit-testable with a
fake transport — no live app, no live network, no real API key.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textutil  # noqa: E402

API_BASE = os.environ.get("YR_VAULT_API_BASE", "http://127.0.0.1:27123")
DEFAULT_TIMEOUT = int(os.environ.get("YR_VAULT_API_TIMEOUT", "20"))


class VaultUnreachable(RuntimeError):
    """The vault's REST interface refused a call, could not be reached, or a write's read-back did
    not confirm what was sent. Raised, never swallowed — a stage that catches this and falls back to
    a filesystem write has misread the rule this class exists to enforce."""


def _http_fetch(method, url, headers, data):
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310 — fixed localhost base
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise VaultUnreachable(f"vault_api: {method} {url} unreachable: {e}") from e


class VaultClient:
    """The one client every machinery write goes through. `api_key`/`base_url` default from the
    environment; `fetch` defaults to the real HTTP transport and is the test seam."""

    def __init__(self, *, api_key=None, base_url=None, fetch=None):
        self.api_key = api_key if api_key is not None else os.environ.get("YR_VAULT_API_KEY", "")
        self.base_url = base_url or API_BASE
        self._fetch = fetch or _http_fetch

    def _require_key(self):
        # non-empty test, never presence (documentation-model.md's own pinned rule): an empty
        # declared value must never read as "authorised".
        if not self.api_key:
            raise VaultUnreachable(
                "vault_api: YR_VAULT_API_KEY is unset or empty — not authorised to write by this "
                "path; stop and ask the human"
            )

    def _call(self, method, path, *, headers=None, data=None):
        self._require_key()
        # vault paths carry spaces and other reserved characters by construction (component/program
        # folder names read as plain prose — "04 projects/..." — never a slug); `quote` with `safe="/"`
        # percent-encodes each segment's own characters while leaving the path's `/` separators alone.
        url = f"{self.base_url}/vault/{urllib.parse.quote(path.lstrip('/'), safe='/')}"
        hdrs = {"Authorization": f"Bearer {self.api_key}"}
        if headers:
            hdrs.update(headers)
        status, body = self._fetch(method, url, hdrs, data)
        if status < 200 or status >= 300:
            raise VaultUnreachable(
                f"vault_api: {method} {path} refused (HTTP {status}): {body[:200]!r}"
            )
        return body

    def read(self, path):
        """The vault file's raw text (never the metadata cache — the vault's own two-authority
        read-back rule: the cache confidently serves stale values with no signal that it is stale)."""
        return self._call("GET", path).decode("utf-8")

    def write(self, path, content):
        """Whole-body create/overwrite (the MCP `vault_write` row's own shape — a raw payload, no
        two-step), then a read-back through the FILE confirming the bytes landed. Raises
        VaultUnreachable on a refusal, an unreachable app, or a read-back mismatch."""
        self._call("PUT", path, headers={"Content-Type": "text/markdown; charset=utf-8"},
                   data=content.encode("utf-8"))
        got = self.read(path)
        if got != content:
            raise VaultUnreachable(
                f"vault_api: read-back mismatch after write to {path!r} — the write did not confirm"
            )
        return got

    def document_map(self, path):
        """The document map's own JSON representation — the plugin's enriched-GET media type
        (`Accept: application/vnd.olrapi.note+json`, the pinned contract's own citation for
        discovering a document's current state; documentation-model.md `:277-278`). The `version`
        field is the concurrency token `patch_section`'s own `if_match` anchors against — reading it
        BEFORE a section edit is how a living reference's repeat edits avoid silently overwriting a
        change made since the last read. Raises `VaultUnreachable` when the call is refused, the body
        does not parse as JSON, or the response carries no `version` field — a fail-loud refusal,
        never a guessed token.

        NOTE (for-the-human, architect.md's own convention for an undecidable item): this wire shape
        is this module's best-faith reading of the pinned contract text, not independently verified
        against the live `/openapi.yaml` — that document's own stated authority
        (documentation-model.md `:278`). Confirm the exact media type and field name against the
        live spec before this runs against the real vault."""
        self._require_key()
        url = f"{self.base_url}/vault/{urllib.parse.quote(path.lstrip('/'), safe='/')}"
        headers = {"Authorization": f"Bearer {self.api_key}",
                  "Accept": "application/vnd.olrapi.note+json"}
        status, body = self._fetch("GET", url, headers, None)
        if status < 200 or status >= 300:
            raise VaultUnreachable(
                f"vault_api: GET {path} (document map) refused (HTTP {status}): {body[:200]!r}"
            )
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise VaultUnreachable(f"vault_api: document map at {path!r} did not parse as JSON: {e}")
        if not isinstance(data, dict) or "version" not in data:
            raise VaultUnreachable(f"vault_api: document map at {path!r} carries no 'version' field")
        return data

    def patch_section(self, path, heading_path, content, *, operation="replace", if_match=None,
                      create_target_if_missing=True):
        """A section edit targeted by heading (`Target-Type: heading`; the pinned contract,
        documentation-model.md `:277-278`) — never a whole-body overwrite, the hazard that
        contract's own concurrency token exists to prevent for a repeatedly-edited living reference.
        `heading_path` is the nested heading's full path, outermost first (e.g. `["## Some
        Section"]` for a top-level heading; `["## Parent", "### Child"]` for a nested one), joined
        by the plugin's own delimiter (`"::"`) into the `Target` header. `operation` is `append` |
        `prepend` | `replace` (default: replace the section's own content — `scope=content`,
        never `markerAndContent`, which would also consume the heading line itself, a destructive
        difference in a vault with no version history). `if_match` rides as the standard HTTP
        conditional-request header (`If-Match`) — the document map's own `version`
        (`document_map()`'s own return); omitted when the caller has no prior document-map read to
        anchor against. Verified by read-back: the new content must appear in the file afterward, or
        this raises `VaultUnreachable` — a substring check, since a section edit touches only PART of
        the document (unlike `write()`'s own whole-body equality check).

        NOTE (for-the-human): same residual caveat as `document_map()` — this wire shape is a
        best-faith reading of the pinned contract, not independently verified against the live
        spec."""
        headers = {"Operation": operation, "Target-Type": "heading",
                  "Target": "::".join(heading_path),
                  "Content-Type": "text/markdown; charset=utf-8"}
        if if_match:
            headers["If-Match"] = if_match
        if create_target_if_missing:
            headers["Create-Target-If-Missing"] = "true"
        self._call("PATCH", path, headers=headers, data=content.encode("utf-8"))
        text = self.read(path)
        if content.strip() not in text:
            raise VaultUnreachable(
                f"vault_api: read-back did not confirm the section edit at {path!r} under "
                f"{'::'.join(heading_path)!r}"
            )
        return text

    def patch_frontmatter(self, path, key, value):
        """A frontmatter key set (`targetType: frontmatter`, `operation: replace`; the *typed-write*
        rule — the value travels as JSON, never hand-quoted YAML). The payload rides in `value`
        (the port correction claimed by process.toml's own `design.stamp.obsidian-mcp` binding: the
        arg is `value`, never `content`). Read back through the file's own frontmatter afterward —
        never the metadata cache."""
        headers = {"Operation": "replace", "Target-Type": "frontmatter", "Target": key,
                   "Content-Type": "application/json"}
        self._call("PATCH", path, headers=headers, data=json.dumps({"value": value}).encode("utf-8"))
        text = self.read(path)
        meta, _ = textutil.split_frontmatter(text)
        if meta.get(key) != value:
            raise VaultUnreachable(
                f"vault_api: read-back did not confirm {key}={value!r} at {path!r} "
                f"(read {meta.get(key)!r})"
            )
        return text
