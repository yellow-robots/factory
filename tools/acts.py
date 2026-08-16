#!/usr/bin/env python3
"""acts.py — act normalization + the typed matcher vocabulary (it-30, the process model).

The wall never sees a raw command string: a per-tool normalizer produces a typed record and the
closed MATCH_KIND selectors match THAT. There is no `substring` and no `regex` member — the shipped
inversion (matching the lawful funnel's file name) is unspellable here.

Purity: normalization is offline. The one declared exception, per the design, is `git-refspec`,
whose extractor resolves a bare `git push`'s target by asking the local repository (bounded, no
network) — the extractor's input is the repository, never the command text.

`cmd | tail` and `a && b` produce multiple segments, each matched independently. An unparseable
command sets `unparsed = True` — a decision input, never a hole.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

# one declared interpreter-unwrap pass — model-design § the normalized act
_UNWRAP = ("python3", "python", "uv", "env", "sh", "bash")

MATCH_KINDS = ("argv", "graphql-mutation", "path-write", "shell-redirect", "mcp-tool", "git-refspec")


_OPERATORS = ("&&", "||", ";", "|", "&")


def _tokens(buf: str) -> list[str]:
    """shlex with `;|&` as punctuation characters, so GLUED operators split too: `x;gh pr merge`
    tokenizes as `x`, `;`, `gh`, ... — the review's evasion where token-level splitting alone left
    a glued command invisible to every wall. Raises ValueError on an unterminated quote."""
    lex = shlex.shlex(buf, posix=True, punctuation_chars=";|&")
    lex.whitespace_split = True
    return list(lex)


def _segments(cmd: str) -> tuple[list[dict], bool]:
    """Per line: shlex first (so a quoted string may CONTAIN newlines and operators — an
    unterminated quote accumulates the next line into the same buffer), then the token list splits
    on operator TOKENS (glued or spaced — see `_tokens`). `cmd | tail` and `a && b` yield
    independent segments; a truly unparseable leftover sets `unparsed` — a decision input, never a
    hole."""
    segs, unparsed = [], False
    buf = ""
    for line in cmd.split("\n"):
        buf = buf + ("\n" if buf else "") + line
        try:
            toks = _tokens(buf)
        except ValueError:
            continue                       # unterminated quote: keep accumulating lines
        buf = ""
        for chunk in _split_on_operators(toks):
            if chunk:
                segs.append(_seg(chunk, raw=line))
    if buf.strip():
        unparsed = True
        segs.append({"raw": buf, "argv": [], "program": "", "subcommands": [],
                     "flags": {}, "operands": []})
    return segs, unparsed


def _split_on_operators(toks: list[str]) -> list[list[str]]:
    out, cur = [], []
    for t in toks:
        if t in _OPERATORS:
            out.append(cur)
            cur = []
        else:
            cur.append(t)
    out.append(cur)
    return out


def _seg(toks: list[str], raw: str = "") -> dict:
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        toks = toks[1:]                    # a bare VAR=value prefix must not hide the program
    toks = _unwrap(toks)
    program = Path(toks[0]).name if toks else ""
    subcommands, flags, operands = [], {}, []
    i, leading = 1, True
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            leading = False
            if "=" in t:
                k, v = t.split("=", 1)
                flags[k] = v
            elif i + 1 < len(toks) and not toks[i + 1].startswith("-"):
                flags[t] = toks[i + 1]
                i += 1
            else:
                flags[t] = ""
        elif leading:
            subcommands.append(t)
        else:
            operands.append(t)
        i += 1
    return {"raw": raw or " ".join(toks), "argv": toks, "program": program,
            "subcommands": subcommands, "flags": flags, "operands": operands}


def _unwrap(toks: list[str]) -> list[str]:
    if not toks:
        return toks
    head = Path(toks[0]).name
    if head in ("sh", "bash") and len(toks) >= 3 and toks[1] == "-c":
        inner, err = [], False
        try:
            inner = shlex.split(toks[2])
        except ValueError:
            err = True
        return inner if inner and not err else toks
    if head == "env":
        rest = [t for t in toks[1:] if "=" not in t or t.startswith("-")]
        return rest or toks
    if head in ("python3", "python", "uv") and len(toks) >= 2 and not toks[1].startswith("-"):
        return toks  # a script invocation keeps its own argv; program stays the interpreter
    return toks


def normalize(tool_name: str, tool_input: dict) -> dict:
    act: dict = {"tool": tool_name, "segments": [], "unparsed": False,
                 "path": "", "fields": dict(tool_input or {})}
    if tool_name == "Bash":
        act["segments"], act["unparsed"] = _segments(tool_input.get("command") or "")
    elif tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        raw = tool_input.get("file_path") or ""
        if raw:
            try:
                act["path"] = str(Path(raw).resolve())
            except OSError:
                act["path"] = str(Path(os.path.normpath(raw)))
        content = tool_input.get("content")
        if content is None:
            content = tool_input.get("new_string")
        act["fields"]["content"] = content
    return act


# ── matchers: one implementation per MATCH_KIND ──────────────────────────────────────────────────

def match(kind: str, spec: dict, act: dict) -> list[dict]:
    """The segments (or a single pseudo-segment) this binding's selector matches on this act.
    Empty list = no match."""
    if kind == "argv":
        return [s for s in act["segments"] if _match_argv(spec, s)]
    if kind == "graphql-mutation":
        return [s for s in act["segments"] if _match_graphql(spec, s)]
    if kind == "path-write":
        return [{"path": act["path"]}] if _match_path(spec, act) else []
    if kind == "shell-redirect":
        return [s for s in act["segments"] if _match_redirect(spec, s)]
    if kind == "git-refspec":
        return [s for s in act["segments"] if _match_refspec(spec, s)]
    if kind == "mcp-tool":
        return [{"fields": act["fields"]}] if _match_mcp(spec, act) else []
    raise ValueError(f"unknown MATCH_KIND {kind!r}")


def _match_argv(spec: dict, seg: dict) -> bool:
    if seg["program"] != spec.get("program"):
        return False
    want = list(spec.get("subcommands") or [])
    if seg["subcommands"][: len(want)] != want:
        return False
    include = spec.get("subcommands_include") or []
    if any(tok not in seg["subcommands"] for tok in include):
        return False
    sc = spec.get("subcommand_contains")
    if sc and not any(sc in tok for tok in seg["subcommands"]):
        return False
    for f, v in (spec.get("flags") or {}).items():
        if f not in seg["flags"]:
            return False
        if v not in ("", None) and seg["flags"][f] != v:
            return False
    if spec.get("flags_any") and not any(f in seg["flags"] for f in spec["flags_any"]):
        return False
    oc = spec.get("operand_contains")
    if oc and not any(oc in o for o in seg["operands"] + list(seg["flags"].values())):
        return False
    return True


def _match_graphql(spec: dict, seg: dict) -> bool:
    if seg["program"] != "gh" or seg["subcommands"][:1] != ["api"]:
        return False
    # Walk the raw argv for EVERY query-carrying argument — a flags dict is last-one-wins, and a
    # duplicated `-f query=` would let an innocent copy shadow the mutating one (review evasion).
    queries = []
    argv = seg["argv"]
    for i, t in enumerate(argv):
        if t in ("-f", "-F", "--field", "--raw-field") and i + 1 < len(argv) \
                and argv[i + 1].startswith("query="):
            queries.append(argv[i + 1][len("query="):])
        elif t.startswith(("-f", "-F")) and "query=" in t:
            queries.append(t.split("query=", 1)[1])
    queries += [o for o in seg["operands"] if "mutation" in o]
    return any(re.search(rf"\b{re.escape(m)}\s*\(", q)
               for q in queries for m in spec.get("mutations") or [])


def _match_path(spec: dict, act: dict) -> bool:
    p = act.get("path") or ""
    if not p:
        return False
    root = spec.get("path_under")
    if root:
        root = os.path.expandvars(root)
        if not root or "$" in root:
            return False  # an unset root can never place a path in scope
        try:
            Path(p).relative_to(Path(root).resolve())
        except (ValueError, OSError):
            return False
    suffix = spec.get("path_suffix")
    if suffix and not p.endswith(suffix):
        return False
    glob = spec.get("path_glob")
    if glob and not Path(p).match(glob):
        return False
    cm = spec.get("content_mentions")
    if cm:
        content = act["fields"].get("content")
        if content is None or cm not in str(content):
            return False
    return True


def _match_redirect(spec: dict, seg: dict) -> bool:
    suffix = spec.get("path_suffix") or ""
    if not suffix:
        return False
    raw = seg.get("raw") or ""
    if not re.search(r">>?|\btee\b|\bcp\b|\bdd\b|\bsed\b.*-i", raw):
        return False
    return suffix in raw


def _match_refspec(spec: dict, seg: dict) -> bool:
    if seg["program"] != "git" or "push" not in seg["subcommands"] + seg["operands"]:
        return False
    targets = set(spec.get("targets") or [])
    ops = [o for o in seg["subcommands"] + seg["operands"]
           if o not in ("push", "origin", "upstream")]
    for o in ops:
        dst = o.split(":", 1)[1] if ":" in o else o
        dst = dst.lstrip("+").removeprefix("refs/heads/")   # +main is a FORCE push, not a new name
        if dst in targets:
            return True
    if not ops:  # bare `git push`: the target is the current branch — ask the repository
        try:
            out = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
            return out.returncode == 0 and out.stdout.strip() in targets
        except (OSError, subprocess.TimeoutExpired):
            return False
    return False


def _match_mcp(spec: dict, act: dict) -> bool:
    tools = spec.get("tools") or ([spec["tool"]] if spec.get("tool") else [])
    if tools and act["tool"] not in tools:
        return False
    for k, v in (spec.get("arg_equals") or {}).items():
        if str(act["fields"].get(k)) != str(v):
            return False
    return True


def cannot_touch_key(act: dict, key: str) -> bool:
    """Act-side evidence for an over-matching frontmatter binding (it-31 slice 1): every visible
    written text can neither open a frontmatter fence (`---`) nor carry the `<key>:` token, so the
    act provably cannot write that frontmatter key. Evidence absent (no visible text) -> False,
    the advisory stands — the same decidable-from-the-act-alone standard the walls already use.
    For Edit acts the removed text counts too: deleting the key's line changes frontmatter."""
    fields = act.get("fields") or {}
    parts = [fields.get("content"), fields.get("old_string")]
    seen = [p for p in parts if isinstance(p, str) and p.strip()]
    if not seen:
        return False
    token = f"{key}:"
    return all("---" not in p and token not in p for p in seen)


# ── value extractors: one implementation per VALUE_KIND. None = UNKNOWN. ─────────────────────────

def extract_value(value_spec: dict, seg: dict, maps: dict[str, dict]) -> str | None:
    kind = value_spec.get("kind")
    if kind == "literal":
        return value_spec.get("literal")
    if kind == "option-id":
        clear_flag = value_spec.get("clear_flag")
        if clear_flag and clear_flag in (seg.get("flags") or {}):
            return value_spec.get("clear_to", "")
        opt = (seg.get("flags") or {}).get(value_spec.get("flag", ""))
        if not opt:
            return None
        table = maps.get(value_spec.get("map", ""), {})
        rev = {v: k for k, v in table.items()}
        return rev.get(opt)
    if kind == "frontmatter-value":
        raw = (seg.get("fields") or {}).get(value_spec.get("arg", "content"))
        return None if raw is None else str(raw).strip().strip('"').strip("'")
    if kind == "flag-literal":
        clear_flag = value_spec.get("clear_flag")
        if clear_flag and clear_flag in (seg.get("flags") or {}):
            return value_spec.get("clear_to", "")
        raw = (seg.get("flags") or {}).get(value_spec.get("flag", ""))
        return raw if raw else None
    if kind in ("graphql-variable", "toml-key", "refspec-target"):
        return None  # not extractable structurally in v1 — UNKNOWN disposes fail-closed
    return None


def selects(selects_when: dict | None, seg: dict, maps: dict[str, dict]) -> bool:
    """Does this segment touch the store this `writes` row covers?"""
    if not selects_when:
        return True
    kind = selects_when.get("kind")
    if kind == "flag-equals":
        want = maps.get("__ids__", {}).get(selects_when.get("source", ""))
        got = (seg.get("flags") or {}).get(selects_when.get("flag", ""))
        return bool(want) and got == want
    if kind == "content-mentions":
        content = (seg.get("fields") or {}).get("content")
        return content is not None and selects_when.get("literal", "") in str(content)
    if kind == "flag-present":
        return any(f in (seg.get("flags") or {}) for f in selects_when.get("flags") or [])
    return False
