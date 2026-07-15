def is_frozen_bench_evidence(rel_path: str) -> bool:
    """Return True iff `rel_path` (a forward-slash repo-relative path) is frozen bench evidence —
    a surface a living-text tree guard (e.g. tools/check_model_refs.py, the version-pin sweep) must
    not read as if it were living documentation.

    Derived rule: frozen evidence surfaces are records, not living docs. A `yr-bench-corpus/1`
    record embeds a past PR's file contents verbatim by design — a sealed replay
    (tools/bench_replay.py) cannot reach git history, so it patches those contents back byte-exact
    from the record; a `yr-bench-result/1` row stores raw check output; a dated report under
    bench/reports/ is frozen once written. A guard asserting "string X appears nowhere in the tree"
    must skip these surfaces, or it fails on history rather than on drift.

    Excluded (fail-closed the *other* direction: scan by default, only these are evidence):
      - bench/results/... and bench/reports/... (any depth under either prefix)
      - bench/corpus/exclusions.jsonl, the append-only exclusion log
      - anything inside a direct subdirectory of bench/corpus/ whose name contains "--" — the
        owner--name shape tools/bench_corpus.py writes one per repo. Recognized structurally as a
        directory-with-something-inside-it (a path with a segment past the "--" directory name),
        never "any subdirectory" of bench/corpus/ — a sibling subdirectory with no "--" in its name
        is not a per-repo record directory and stays scanned.

    NOT excluded, overriding all of the above: any path whose basename is "README.md" — a living
    doc is never evidence, wherever it lands under bench/ (bench/corpus/README.md is the living
    grading-caveat contract tools/bench_report.py quotes verbatim into every report; the same logic
    would protect a README.md dropped under bench/results/ or bench/reports/). Also not excluded:
    other top-level files of bench/corpus/, and everything outside bench/ entirely.
    """
    parts = rel_path.split("/")
    if parts[-1] == "README.md":
        return False
    if rel_path.startswith("bench/results/") or rel_path.startswith("bench/reports/"):
        return True
    if rel_path == "bench/corpus/exclusions.jsonl":
        return True
    if len(parts) >= 4 and parts[0] == "bench" and parts[1] == "corpus" and "--" in parts[2]:
        return True
    return False


def _unquote(item: str):
    """Strip a wrapping pair of double quotes from one scalar/list-item token, verbatim inside."""
    if item.startswith('"'):
        end = item.find('"', 1)
        return item[1:end] if end != -1 else item[1:]
    return item


def _parse_value(raw: str):
    """Parse one frontmatter scalar/list value from the text after `key:`."""
    if raw == "":
        return ""
    if raw.startswith('"'):                       # double-quoted: keep contents verbatim (incl. '#')
        return _unquote(raw)
    if raw.startswith("["):                       # inline list [a, b, c]
        end = raw.find("]")
        if end != -1:
            inner = raw[1:end].strip()
            return [] if inner == "" else [_unquote(item.strip()) for item in inner.split(",")]
    hash_idx = raw.find(" #")                      # unquoted scalar: drop a trailing ' # comment'
    if hash_idx != -1:
        raw = raw[:hash_idx].rstrip()
    return raw


def split_frontmatter(text: str):
    """Split leading YAML-ish frontmatter from a markdown document → (meta, body).

    `meta` maps each frontmatter key to its value — a string, or a list for inline
    `[a, b]` syntax or a block style (a bare `key:` line followed by indented `- item`
    lines — the form Obsidian's property editor writes for a non-empty list). Parses
    only the small subset our templates use (no external YAML dependency): `key: value`
    lines, double-quoted values (list items too), inline/block lists, and a trailing
    ` # comment` on unquoted values. Obsidian auto-adds `created`/`updated` keys — those
    are preserved like any other (we never reject unknown keys). Text that does not open
    with a `---` line and close with another `---` is treated as having no frontmatter,
    and returned unchanged as the body.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.split("\n")
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:                             # no closing fence → not frontmatter
        return {}, text
    meta = {}
    i = 1
    while i < close:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            i += 1
            continue
        key, _, raw = line.partition(":")
        raw = raw.strip()
        if raw == "":                              # maybe a block-style list follows
            items = []
            j = i + 1
            while j < close:
                item_line = lines[j]
                item_stripped = item_line.strip()
                if item_line[:1] in (" ", "\t") and (item_stripped == "-" or item_stripped.startswith("- ")):
                    items.append(_unquote(item_stripped[1:].strip()))
                    j += 1
                else:
                    break
            if items:
                meta[key.strip()] = items
                i = j
                continue
        meta[key.strip()] = _parse_value(raw)
        i += 1
    return meta, "\n".join(lines[close + 1:])
