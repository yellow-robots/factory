#!/usr/bin/env python3
"""vault_api.py — the machinery's one client of the vault's REST interface (it-36 slice F).

The plugin (obsidian-local-rest-api) serves plaintext HTTP on `127.0.0.1:27123` only (`27124` is its
conventional HTTPS port, off on this vault); its served `/openapi.yaml` is the authority over the
wire contract, never memory (skills/factory/references/documentation-model.md's own "Editing safely"
pin, :250-261). A human session speaks to the vault through the app's MCP tools; a cold machinery
process has no MCP registration, so this is its own equivalent path over the SAME underlying REST
surface — read, whole-body write, a section edit by heading, and a frontmatter-key patch — never a
direct filesystem mutation (the vault is "live + synced": app-mediated writes only).

PATCH wire shape (it-36 slice H, #473 fold, 2026-09-06): verified live against `curl -s
http://127.0.0.1:27123/openapi.yaml` (read-only), never from memory, per this module's own opening
rule. The server's default (2.0) PATCH mode carries the WHOLE instruction as a JSON request body —
`{"targetType", "target", "operation", "content"|"value", "createTargetIfMissing", "ifMatch", ...}`
— no `Target-Type`/`Target` HEADERS and no `Markdown-Patch-Version` at all; that header form is
either the deprecated 1.x engine (requires `Markdown-Patch-Version: 1`) or raw-content mode
(requires an explicit `Markdown-Patch-Version: 2`, with `Target` as percent-encoded JSON) — sending
those headers with NEITHER version set is rejected outright, `400
PatchHeaderTargetingRequiresExplicitVersion`. A heading `target` is the PLAIN heading text array,
outermost first (`["Parent", "Child"]`) — never `#`/`##`-prefixed, never `::`-joined (that join is
the deprecated 1.x-only `Target-Delimiter` convention).

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
        """The document map's own JSON representation — `Accept: application/vnd.olrapi.document-
        map+json` (the real server's enriched-GET media type for PATCH-target discovery; verified
        2026-09-06 against the live `/openapi.yaml`, `GET /vault/{path}` — the `note+json` media
        type is a DIFFERENT representation, NoteJson, that carries no `version` at all; sending it
        here would make every real call raise, unreachable by construction). The `version` field is
        the concurrency token `patch_section()`'s own `if_match` anchors against — reading it BEFORE
        a section edit is how a living reference's repeat edits avoid silently overwriting a change
        made since the last read (`PATCH`'s own `412 Precondition Failed` on a stale token). Raises
        `VaultUnreachable` when the call is refused, the body does not parse as JSON, or the response
        carries no `version` field — a fail-loud refusal, never a guessed token."""
        self._require_key()
        url = f"{self.base_url}/vault/{urllib.parse.quote(path.lstrip('/'), safe='/')}"
        headers = {"Authorization": f"Bearer {self.api_key}",
                  "Accept": "application/vnd.olrapi.document-map+json"}
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

    def _patch_instruction(self, path, instruction):
        """The one PATCH wire call both `patch_section`/`patch_frontmatter` share: the server's
        default (2.0) JSON-instruction-body mode — `Content-Type: application/json`, the whole
        `PatchInstruction` object as the body, NO targeting headers and NO `Markdown-Patch-Version`
        at all (verified 2026-09-06 against the live `/openapi.yaml`'s `PATCH /vault/{path}`: the
        deprecated 1.x `Target-Type`/`Target` HEADER form — this client's own shape before this fix —
        is rejected outright without an explicit `Markdown-Patch-Version`, `400
        PatchHeaderTargetingRequiresExplicitVersion`; the JSON-instruction body needs no such
        header at all, since it isn't the header form). Returns the raw response body (the server's
        own 200 response IS the patched document, but every caller here still re-`read()`s the file
        afterward — this client's own paranoid convention, never trusting a mutation's own claimed
        response over an independent read)."""
        self._call("PATCH", path, headers={"Content-Type": "application/json"},
                  data=json.dumps(instruction).encode("utf-8"))

    def patch_section(self, path, heading_path, content, *, operation="replace", if_match=None,
                      create_target_if_missing=True):
        """A section edit targeted by heading — the JSON-instruction body's own `targetType:
        "heading"` (verified 2026-09-06 against the live `/openapi.yaml`'s `PatchInstruction`
        schema and its `PATCH /vault/{path}` examples) — never a whole-body overwrite, the hazard
        the `ifMatch` concurrency token exists to prevent for a repeatedly-edited living reference.
        `heading_path` is the nested heading's full path, outermost first, as PLAIN HEADING TEXT —
        e.g. `["Some Section"]` for a top-level heading, `["Parent", "Child"]` for a nested one —
        NEVER a leading `#`/`##` (the server's own `target` field takes exactly the array of heading
        texts; a `#` prefix becomes part of the heading text itself, not stripped). `operation` is
        `append` | `prepend` | `replace` (default: replace the section's own body — `scope=content`,
        never `markerAndContent`, which would also consume the heading line itself, a destructive
        difference in a vault with no version history). `if_match` rides as the instruction's own
        `ifMatch` field — the document map's own `version` (`document_map()`'s own return); omitted
        when the caller has no prior document-map read to anchor against. Verified by read-back: the
        new content must appear in the file afterward, or this raises `VaultUnreachable` — a
        substring check, since a section edit touches only PART of the document (unlike `write()`'s
        own whole-body equality check)."""
        instruction = {"targetType": "heading", "target": list(heading_path), "operation": operation,
                      "content": content, "createTargetIfMissing": bool(create_target_if_missing)}
        if if_match:
            instruction["ifMatch"] = if_match
        self._patch_instruction(path, instruction)
        text = self.read(path)
        if content.strip() not in text:
            raise VaultUnreachable(
                f"vault_api: read-back did not confirm the section edit at {path!r} under "
                f"{heading_path!r}"
            )
        return text

    def patch_frontmatter(self, path, key, value):
        """A frontmatter key set — the JSON-instruction body's own `targetType: "frontmatter"`,
        `operation: "replace"` (verified 2026-09-06 against the live `/openapi.yaml`; this client
        previously sent `Target-Type`/`Target` HEADERS plus a `{"value": v}` body, which the real
        server rejects outright without an explicit `Markdown-Patch-Version` — and even WITH one,
        under raw-content mode a JSON body IS the `value` carrier directly, so `{"value": v}` would
        have set the key to that whole wrapper object, never to `v` itself). The *typed-write* rule
        still holds — the value travels as the instruction's own `value` field, JSON-typed, never
        hand-quoted YAML — `createTargetIfMissing` set, since this client's callers set fields
        (`status`, `superseded_by`) that may not already exist. Read back through the file's own
        frontmatter afterward — never the metadata cache."""
        instruction = {"targetType": "frontmatter", "target": key, "operation": "replace",
                      "value": value, "createTargetIfMissing": True}
        self._patch_instruction(path, instruction)
        text = self.read(path)
        meta, _ = textutil.split_frontmatter(text)
        if meta.get(key) != value:
            raise VaultUnreachable(
                f"vault_api: read-back did not confirm {key}={value!r} at {path!r} "
                f"(read {meta.get(key)!r})"
            )
        return text
