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


# The two named anchoring modes a `YR-*` record-marker reader may require. Deliberately distinct — a
# caller names the one it needs, and the helper never guesses between them nor collapses them into one.
MARKER_SENTINEL = "sentinel"
MARKER_PREFIX = "prefix"


def marker_line_matches(line: str, marker: str, *, mode: str) -> bool:
    """The one shared matcher for every `YR-*` record marker in the tree: does a single `line` carry
    `marker` under the named anchoring `mode`? The caller iterates its own lines (`body.splitlines()`)
    and owns what a match MEANS (a whole body, a 1-indexed line number, the text after the marker) — this
    helper judges exactly one line, under exactly one of two deliberately-distinct rules:

      * ``mode="sentinel"`` — the line, after ``.strip()``, is EXACTLY `marker`. Leading (and trailing)
        whitespace is tolerated BY DESIGN, so an indented sentinel line still matches; a prose mention or
        an inline-backticked example on a longer line does not.
      * ``mode="prefix"`` — the line's RAW, unstripped text begins with `marker` at column 0
        (``line.startswith(marker)``), with NO whitespace tolerance: an indented line, a ``> ``-blockquoted
        line, or an inline mention never matches — the anchor guarantees the marker leads its own physical
        line (the bench-transcript guard).

    The difference between the two is deliberate and load-bearing; the helper never unifies them. An
    unrecognized `mode` is a programming error, raised rather than guessed.
    """
    if mode == MARKER_SENTINEL:
        return line.strip() == marker
    if mode == MARKER_PREFIX:
        return line.startswith(marker)
    raise ValueError(
        f"marker_line_matches: unknown mode {mode!r} (expected {MARKER_SENTINEL!r} or {MARKER_PREFIX!r})")


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


class FrontmatterMeta(dict):
    """The mapping `split_frontmatter` returns for the frontmatter it parsed, carrying an
    `out_of_subset` list alongside it. In every dict respect — equality, iteration, `.get` —
    this is an ordinary dict, so the 2-tuple `(meta, body)` contract and every existing caller
    are unchanged; the extra attribute is the reporting channel for frontmatter the splitter
    deliberately does not parse. Empty `out_of_subset` ⇒ every key was inside the declared subset.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.out_of_subset = []


def _indent(line: str) -> int:
    """Leading-whitespace width (spaces or tabs) — a top-level key sits at indent 0."""
    return len(line) - len(line.lstrip(" \t"))


def _is_list_item(stripped: str) -> bool:
    """True for a block-list item token: a bare `-` or a `- value` (already `.strip()`ed)."""
    return stripped == "-" or stripped.startswith("- ")


def split_frontmatter(text: str):
    """Split leading YAML-ish frontmatter from a markdown document → (meta, body).

    `meta` is a `FrontmatterMeta` (a dict) mapping each in-subset frontmatter key to its value —
    a string, or a list for inline `[a, b]` syntax or a block style (a bare `key:` line followed
    by indented `- item` lines — the form Obsidian's property editor writes for a non-empty list).
    We parse only the small subset our templates use (no external YAML dependency): `key: value`
    lines, double-quoted values (list items too), inline/block lists, and a trailing ` # comment`
    on unquoted values. Obsidian auto-adds `created`/`updated` keys — those are preserved like any
    other (we never reject unknown keys). Text that does not open with a `---` line and close with
    another `---` is treated as having no frontmatter, and returned unchanged as the body.

    Frontmatter *outside* that declared subset is REPORTED, never guessed: each such shape is
    described in `meta.out_of_subset` and its lines are consumed so they cannot fabricate a
    top-level key nor overwrite a real one. In-subset keys around it still parse to their true
    values (the report augments a partial parse; it never replaces it with an empty mapping).
    "Outside the declared subset" is exactly this enumerated set:
      1. a nested mapping — a bare `key:` whose indented children are `key: value` lines, not `- item`;
      2. a block scalar — `key: |` or `key: >` (with any chomp/indent indicator);
      3. a wrapped plain-scalar continuation — a `key: value` line folding onto an indented next line;
      4. a block list at zero indentation — `- item` lines flush against the left margin;
      5. a bracketed inline list we cannot fully parse — a `key: [...` with no closing `]` on the line;
      6. a value beginning with `&` — a YAML anchor.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return FrontmatterMeta(), text
    lines = text.split("\n")
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:                             # no closing fence → not frontmatter
        return FrontmatterMeta(), text

    def _skip_children(start):
        """Advance past the run of blank/indented lines that belong to the key at `start - 1`."""
        j = start
        while j < close and (not lines[j].strip() or _indent(lines[j]) > 0):
            j += 1
        return j

    meta = FrontmatterMeta()
    i = 1
    while i < close:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if _indent(line) > 0:                     # an orphaned continuation / nested child
            meta.out_of_subset.append(
                f"indented line outside the subset (nested mapping / continuation): {stripped!r}")
            i += 1
            continue
        if _is_list_item(stripped):               # (4) block list at zero indentation
            meta.out_of_subset.append(
                f"block list at zero indentation outside the subset: {stripped!r}")
            i += 1
            while i < close and _indent(lines[i]) == 0 and _is_list_item(lines[i].strip()):
                i += 1
            continue
        if ":" not in line:                       # a bare scalar / stray text at column 0
            meta.out_of_subset.append(f"line outside the subset (no key): {stripped!r}")
            i += 1
            continue

        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()

        if raw[:1] in ("|", ">"):                 # (2) block scalar
            meta.out_of_subset.append(f"{key!r}: block scalar (`{key}: {raw}`) outside the subset")
            i = _skip_children(i + 1)
            continue
        if raw[:1] == "&":                        # (6) anchor value
            meta.out_of_subset.append(f"{key!r}: anchor value (`{raw}`) outside the subset")
            i = _skip_children(i + 1)
            continue
        if raw == "":                             # bare key: block list, nested mapping, or empty
            j = i + 1
            while j < close and lines[j].strip() and _indent(lines[j]) > 0:
                j += 1
            children = lines[i + 1:j]
            if children and all(_is_list_item(c.strip()) for c in children):
                meta[key] = [_unquote(c.strip()[1:].strip()) for c in children]
                i = j
                continue
            if children:                          # (1) nested mapping / mixed indented block
                meta.out_of_subset.append(
                    f"{key!r}: nested block outside the subset (not a plain `- item` list)")
                i = j
                continue
            meta[key] = ""                        # genuinely empty scalar (in subset)
            i += 1
            continue
        if raw[:1] == "[":                        # inline list
            if raw.find("]") != -1:
                meta[key] = _parse_value(raw)     # in-subset: fully bracketed on this line
                i += 1
                continue
            meta.out_of_subset.append(            # (5) bracketed list we cannot fully parse
                f"{key!r}: inline list without a closing ']' outside the subset (`{raw}`)")
            i = _skip_children(i + 1)
            continue

        j = i + 1                                 # plain scalar — unless a continuation folds in
        while j < close and lines[j].strip() and _indent(lines[j]) > 0:
            j += 1
        if j > i + 1:                             # (3) wrapped plain-scalar continuation
            meta.out_of_subset.append(f"{key!r}: wrapped plain-scalar continuation outside the subset")
            i = j
            continue
        meta[key] = _parse_value(raw)
        i += 1
    return meta, "\n".join(lines[close + 1:])
