# State model format — panel synthesis

## Winner

THE MINIMALIST as the base — grafted with THE ADVERSARY's structural loader checks and derived stance, and THE LONG GAME's per-guard `why`, vendor seam, and decay instruments. Shipped as `process.toml` + `tools/process.py`, deliberate siblings of `records.toml` + `tools/records.py`.

## Rationale

THE MINIMALIST won two of three judging axes (surface generation, authorability) and it won them for the same reason: its transition row is the only one a tired human can read at a glance, and its lane compiler is the only one that, when I actually traced it against the shipped `records.toml:387-391`, reproduces the detector's data. I ran that trace as code, not by eye. THE ADVERSARY's and THE LONG GAME's effects-only lane rule compiles the `design` lane EMPTY (their `design_doc.draft->active` has no record effect; `YR-DESIGN-REVIEW` and `YR-DESIGN-FIT` are guards) — it silently deletes the detector's whole job. That is disqualifying for a base.

But THE MINIMALIST loses axis 2, and it loses it on the exact defect it claims to kill. Its rule `prevented <=> >=1 binding AND every non-funnel binding has complete = true` is satisfied VACUOUSLY by a transition that declares only its funnel. Delete two `[[transition.binding]]` stanzas from its own worked example (c) and the loader is happy while the map asserts prevention over a wide-open path. That is the shipped defect re-spellable in three deleted lines. It also leaves `stance` authorable with `defer` in the vocabulary (a one-word fail-open wall), gives the Reason-clearing rule a place to be written but nothing that forces it, and explicitly refuses a home for 2 of the 8 shipped walled rows.

So the synthesis keeps the Minimalist's shape and takes the three devices that close those holes, each judged salvageable by a judge who was not its author:

1. **Coverage is an obligation of the STORE, not a choice of the binding author** (Adversary). `[[store.write_path]]` enumerates every known way to write the store with an `observable` flag; an observable path with no live binding is a LOAD ERROR. Prevention-by-omission becomes a build failure.
2. **Stance and enforcement are derived, with no field to author** (Adversary). Shipping a fail-open wall requires first lying about `door` — a word sitting next to `to` in a five-line diff.
3. **Predicates are pure over fetched `[[source]]` blobs** (Long Game). This is the correct root cause of one-grammar-three-implementations: in the shipped tree `wall._trail_has`, `wall.board_check` and `wall.promote_check` each FETCH and JUDGE, so each grew its own judge. Remove the fetch and the motive is gone, not just the rule.

Three things I designed rather than grafted, because every proposal's version was worse:

- **Per-facet partition instead of the Adversary's C1 store-product partition.** C1 demands all 5x3 = 15 Status/Reason cells be named as states before the file loads, scaling multiplicatively. Per-facet ("each facet's states' values are a permutation of its store's values") is linear, achieves the same kill — `reason = ""` becomes the named state `none`, so a state's meaning is never ambiguous — and removes the Minimalist's `from = ["*"]` escape hatch, which its own author called "easy to overuse."
- **Two facet-disposal loader rules that prove BOTH halves of the brief's first constraint.** F1: a guard on a non-primary facet REQUIRES a post disposing that facet — omit `facet_is(reason, none)` on the unblock and the model does not load. F2: a post on an unguarded non-primary facet is FORBIDDEN unless declared — ADD a Reason clear to the fresh Backlog promote and the model does not load. The Adversary got both from subset math nobody will re-derive at 2am; this is two sentences.
- **A stance derivation with no `door`-driven fail-open cell.** The Adversary's table maps `reversible/execute` + guards-FALSE to `advise`, which would make record-before-flip advisory for the unblock — against the canon. Here guards-FALSE is ALWAYS refuse; `advise` is reachable only from a binding declaring itself `over-matching`, which is principled (a binding that fires on acts it cannot confirm must not deny). `door` then does real structural work instead: `door = "one-way"` forbids `agent_may = "execute"`, which makes the escalation valve MANDATORY at one-way doors rather than optional — the `ask` transport the canon called for and the shipped code never implemented.

Everything is TOML that I parsed with `tomllib` before writing it down. All three proposals shipped worked examples that do not load (`;` as a key separator; multi-line inline tables; multi-line basic strings) — in a round whose whole subject is that the last artifact was not verified.

## Schema

`process.toml` at the repo root; `tools/process.py` (loader + CLI + compilers); `tools/predicates.py` (one implementation per predicate, pure); `tools/sources.py` (ALL I/O); `tools/acts.py` (act normalizer + typed matchers). Stdlib only, Python 3.11, `tomllib`.

## Closed vocabularies — in `tools/process.py`, mirroring `records.py`'s MODES/SURFACES discipline

Declared in code and documented in the file header, never as data rows (a vocabulary declared twice is a vocabulary that disagrees with itself):

```python
CONTRACT   = "yr-process/1"
PORT       = "port."     # the seam marker; the one-way reference rule is loader-enforced

ACTORS     = ("human", "attended-agent", "machinery", "external-service")
AGENT_MAY  = ("execute", "propose")          # read only when "attended-agent" is in actor
DOOR       = ("one-way", "reversible")       # CONSEQUENCES, never diffs
STANCE     = ("refuse", "escalate", "advise", "observe")      # DERIVED — no field exists
ENFORCE    = ("prevented", "detected", "partial", "unenforced")  # DERIVED — no field exists
PREDICATES = ("facet_is", "store_is", "record_present", "record_absent",
              "evaluator_pass", "act_field_contains")          # closed; admission rule below
STORE_KIND = ("board-single-select", "frontmatter-key", "pr-attribute", "git-ref",
              "host-file", "manifest-key", "issue-field")
MATCH_KIND = ("argv", "graphql-mutation", "path-write", "shell-redirect",
              "mcp-tool", "git-refspec")     # NO substring, NO regex — see `bindings`
VALUE_KIND = ("option-id", "literal", "frontmatter-value", "graphql-variable",
              "toml-key", "refspec-target")
PRECISION  = ("exact", "over-matching")      # an over-matching binding may never refuse
DECAY      = ("fresh", "stale", "drifted", "broken")           # COMPUTED — no field exists
AMEND_KIND = ("widen", "narrow", "port", "decay-repair", "editorial")
VENDORS    = ("neutral", "github", "anthropic-claude-code", "obsidian", "git", "host")
SURFACES   = records.SURFACES                # IMPORTED from records.py, never restated
```

## The two derivation tables the loader owns (code, not data)

```
STANCE(caller, transition, guards, binding):
    if caller not in transition.actor:        refuse   # categorical for this class; guards unread
    elif any guard is not TRUE:               refuse   # FALSE and UNKNOWN are the same answer
    elif caller == "attended-agent"
         and transition.agent_may == "propose":  escalate
    else:                                     observe
    then: if binding.precision == "over-matching" and result in (refuse, escalate): advise

ENFORCEMENT(transition):
    paths = every [[store.write_path]] of every store the transition's posts write
    live  = a path with >=1 binding covering it whose DECAY is "fresh"
    open  = [p for p in paths if not live(p)]        # includes every observable=false path
    detected = transition has >=1 record_present post, or every open path names detected_by
    prevented  if open == []
    partial    if live paths exist and (open or detected)
    detected   if no live path and detected
    unenforced otherwise

DECAY(binding):
    "drifted" if probe fingerprint != live fingerprint
    "broken"  if the binding's last `verify` run failed
    "stale"   if today - verified_on > recheck_days
    "fresh"   otherwise
```

## Loader rules — each earned from a named defect

Strict **unknown-key rejection per table**: a key not in that table's `ALLOWED_KEYS` is a load error. This is what makes several kills real — a field cannot be smuggled where it does not belong.

- **P (partition, per facet):** a facet's `[[state]]` values must be a permutation of its store's `values` — each exactly once. *Kills: an ambiguous state, and the need for a `from = ["*"]` wildcard.*
- **F1 (facet disposal required):** if a transition guards on a NON-PRIMARY facet, its `post` list must contain a predicate writing that facet. *This is the Reason-clearing rule's home. Omit it and the model does not load.*
- **F2 (facet disposal forbidden):** a `post` on a non-primary facet the transition does NOT guard on is a load error unless the facet is listed in `writes_unguarded_facets` with a `why`. *This is the other half: a fresh Backlog promote must NOT clear Reason.*
- **D (one-way doors escalate):** `door = "one-way"` forbids `agent_may = "execute"`. *An agent never walks through a one-way door silently; it proposes and the human answers.*
- **A (actor/agent_may coherence):** `agent_may` must be absent unless `"attended-agent"` is in `actor`.
- **C (coverage):** a `guarded = true` store with an `observable = true` write path that no binding covers is a load error naming the store and the path. *Kills prevention-by-omission.*
- **C2 (named holes):** an `observable = false` write path must declare `detected_by` (a registered record) or `undetectable = true` with a reason. Every binding must carry a non-empty `does_not_cover`. *Honesty costs one line; dishonesty requires inventing a false one.*
- **R (registry citation):** every `record_present`/`record_absent` argument must resolve in `records.toml`. The predicate takes NO surface argument — the registry row routes the read, so a wrong-surface guard is unspellable.
- **S (satisfiability):** a guard `record_present(R)` is satisfiable only if R's `emitted_by` (a NEW typed column this design adds to `records.toml` — see the migration note) includes an actor class other than the transition's own actors, OR R is a `post` of another declared transition. *Kills "a walled row whose stated condition has no satisfiable path".*
- **V (vocabulary):** a `predicate` outside PREDICATES is a load error. **Prose conditions are unwritable.**
- **Seam:** no neutral row may contain a string beginning `port.`; no `port.*` row may be referenced from a neutral row.
- **Sinks:** `[observability]` is the only table that may name a sink, and `may_influence_decisions = false` / `written = "after-decision"` are constants the loader refuses to flip.
- **Determinism:** if two transitions survive selection for the same `(store, value, current-state, caller)`, `process.py validate` fails. Runtime never picks between rules.

## The file

Every construct below was round-tripped through `tomllib` before being written here.

```toml
# process.toml — the factory's machine-readable process model. Sibling of records.toml.
#
# Four surfaces compile from this file and are NEVER hand-authored:
#   1. the walled-act map              process.py compile acts   -> build/walled-acts.md
#   2. the detector's lane mandates    process.py compile lanes  -> build/lanes.toml
#   3. the session-start slice         process.py compile slice  -> hooks/deliver.sh
#   4. the close report                process.py compile close  -> Stop additionalContext
#   (+ build/conformance.json — generated test vectors; the promises reach the code)
#
# Record GRAMMARS are cited by name from records.toml and never restated. There is no field in
# this schema in which a marker, a regex, or a field list can be spelled.
#
# THERE IS NO `stance` FIELD AND NO `enforcement` FIELD. Both are derived. A fail-open wall
# cannot be typed; it can only be lied into existence by mislabelling a `door`, which is one
# semantically loaded word sitting next to `to` in the diff.

[model]
contract = "yr-process/1"
version = "1.0.0"                       # semver; every diff bumps it (process.py check --amendment)
records_registry = "records.toml"
change_duty = "gate-touching"           # the only legal value; compiled into the slice's footer
slice_max_bytes = 12000                 # compile_slice.py's shipped bound, carried over
compiled = ["build/walled-acts.md", "build/lanes.toml",
            "build/slice-static.md", "build/conformance.json"]

# ── the human's anchor when reading a gate-touching diff ─────────────────────────────────────
[[amendment]]
version = "1.0.0"
date = "2026-08-08"
kind = "widen"                          # AMEND_KIND
touches = ["task.blocked->ready.unblock", "task.backlog->ready.standalone"]
reason = "the Reason-clearing postcondition had no home; walls were bound to mechanisms"
review = "yellow-robots/factory#420"    # where THIS diff's independent review lives
who = "@jbrey"

# ── authority boundary: plugin hooks are USER-scoped, so the lane must know where it ends ────
[boundary]
marker_files = [".yr/factory.toml"]     # any ancestor carrying one is factory-governed
roots = ["$YR_WORKSPACE", "$YR_VAULT_ROOT"]
outside_scope = "observe"               # never refuse outside our world
caller_env = "YR_CALLER"                # the DECLARED caller class — never sniffed from the env
caller_default = "attended-agent"       # fail-closed: the walled class is the default, so a test
                                        # must opt OUT of enforcement, never into it
caller_trust = "declared"               # printed verbatim in every compiled surface: this is a
                                        # speed bump and the model says so out loud

# ── observability: constants, so a reviewer sees them in the diff ────────────────────────────
[observability]
journal = "$YR_WALL_STATE/journal.jsonl"
written = "after-decision"              # constant; the loader rejects any other value
may_influence_decisions = false         # constant; the loader rejects `true`
best_effort = true                      # constant; the loader rejects `false`

# ── sources: the ONLY I/O. Predicates are pure functions over what a source fetched. ─────────
[[source]]
id = "issue-trail"
fetches = "the issue body plus every comment body, page-safe (the nit_harvest pagination loop)"
impl = "tools/sources.py:issue_trail"
vendor = "github"
timeout_s = 20
cache = "per-decision"

[[source]]
id = "board-item"
fetches = "the ProjectV2 item fronting an issue: its field values plus updatedAt"
impl = "tools/sources.py:board_item"
vendor = "github"
timeout_s = 20
cache = "per-decision"

# (further sources: pr-trail, vault-doc, manifest-at-base-tip, host-file, git-refs, act-payload)

# ── stores: where a state PHYSICALLY lives. No state without one. ────────────────────────────
[[store]]
id = "board.status"
kind = "board-single-select"            # STORE_KIND
vendor = "github"
location = "Projects v2 single-select STATUS on the shared 'Yellow Robots - Dev' board"
identifiers = "tools/board_plumbing.py:status_field_id, :status_opt"   # CITED, never copied
values = ["Backlog", "Ready", "In Progress", "In Review", "Done"]
read = "source.board-item"
writable_by = ["human", "attended-agent", "machinery", "external-service"]  # the permission tier
guarded = true                          # -> write-path coverage is ENFORCED (loader rule C)
change_clock = "ProjectV2Item.updatedAt"   # enables guard `window = "since-store-change"`
unknown_value_policy = "unknown"        # constant: a read outside `values` is UNKNOWN, never
                                        # coerced to the nearest legal value

  # Every KNOWN way to write this store. Rule C makes an uncovered observable path a LOAD ERROR.
  # NOTE what is absent: `tools/board_plumbing.py set-field` is NOT a write path. It shells out to
  # `gh project item-edit`, so it is covered by the gh-cli row like every other caller. The shipped
  # wall matched the literal string "board_plumbing.py" — i.e. the lawful, self-checking door — and
  # so denied the funnel while leaving every bypass open. Here there is nothing to match: coverage
  # is declared per EFFECT PATH, and an implementation file is not a path.
  [[store.write_path]]
  id = "gh-cli"
  how = "gh project item-edit --field-id <STATUS> --single-select-option-id <OPT>"
  observable = true

  [[store.write_path]]
  id = "graphql"
  how = "updateProjectV2ItemFieldValue / clearProjectV2ItemFieldValue from any GraphQL client"
  observable = true

  [[store.write_path]]
  id = "web-ui"
  how = "a human moving the card, or GitHub's native close->Done automation"
  observable = false                    # -> automatically an open path in every honesty block
  detected_by = "YR-BOARD-FLIP"         # required by rule C2 when observable = false

[[store]]
id = "board.reason"
kind = "board-single-select"
vendor = "github"
location = "Projects v2 single-select REASON on the same board"
identifiers = "tools/board_plumbing.py:reason_field_id, :reason_opt"
values = ["", "Needs-info", "Blocked"]  # "" is a real value; it becomes the named state `none`
read = "source.board-item"
writable_by = ["human", "attended-agent", "machinery"]
guarded = true
change_clock = "ProjectV2Item.updatedAt"

  [[store.write_path]]
  id = "gh-cli"
  how = "gh project item-edit --field-id <REASON> (--single-select-option-id <OPT> | --clear)"
  observable = true

  [[store.write_path]]
  id = "graphql"
  how = "updateProjectV2ItemFieldValue / clearProjectV2ItemFieldValue"
  observable = true

  [[store.write_path]]
  id = "web-ui"
  how = "the Projects UI"
  observable = false
  detected_by = "YR-BOARD-FLIP"

# (further stores, same shape: pr.merged · doc.frontmatter.status · manifest.auto_merge ·
#  host.merge_sentinel · git.ref.protected — each with its own write_path enumeration)

# ── machines: facets are ORDERED; facets[0] is PRIMARY and is what transitions move ──────────
[[machine]]
id = "task"
subject = "one GitHub issue of Type Task or Epic, as it sits on the shared Dev board"
scope = "repo+issue"                    # how ONE instance is addressed
facets = ["status", "reason"]
note = "RFC 0003's state machine. Reason is the off-track facet, normalised out of Status."

# ── states: id + the LITERAL stored value. Rule P: a facet's values are a permutation of the
#    store's `values`, each exactly once. A state whose storage cannot be named is unwritable. ─
[[state]]
machine = "task"
facet = "status"
id = "backlog"
store = "board.status"
value = "Backlog"
initial = true

[[state]]
machine = "task"
facet = "status"
id = "ready"
store = "board.status"
value = "Ready"

[[state]]
machine = "task"
facet = "status"
id = "in-progress"
store = "board.status"
value = "In Progress"

[[state]]
machine = "task"
facet = "status"
id = "in-review"
store = "board.status"
value = "In Review"

[[state]]
machine = "task"
facet = "status"
id = "done"
store = "board.status"
value = "Done"
terminal = true

[[state]]
machine = "task"
facet = "reason"
id = "none"
store = "board.reason"
value = ""                              # naming the cleared field is what lets a post write it

[[state]]
machine = "task"
facet = "reason"
id = "needs-info"
store = "board.reason"
value = "Needs-info"

[[state]]
machine = "task"
facet = "reason"
id = "blocked"
store = "board.reason"
value = "Blocked"

# ── lanes: names and scope only. MEMBERSHIP IS DERIVED from transition.lane. ─────────────────
[[lane]]
id = "standalone"
subject = "a standalone task with no governing design"
scope = "repo+issue"

# ── evaluators: the delegation seam. DELEGATE, never re-implement. ───────────────────────────
[[evaluator]]
id = "merge"
argv = ["python3", "tools/merge_shadow.py", "evaluate", "--repo", "{scope.repo}", "--pr", "{scope.pr}"]
conditions_display = ["ci_green", "freshness", "terminal_approval", "rank_gate", "sentinel", "shadow_complete"]
timeout_s = 120
contract = "exit 0 pass; exit 1 fail with the failed-condition id as stdout's first line; any other code, a timeout or an OSError is UNKNOWN"
note = """The six merge conditions are ITS conditions, in ITS order, with ITS fail-closed
semantics. This model holds no copy: `conditions_display` is a DISPLAY list so the slice can say
"still needs: freshness" without this model knowing what freshness is, and the loader never
evaluates it. Six guard rows here would have been six second implementations."""

# ── transitions: the ONLY table a guard can attach to. ───────────────────────────────────────
[[transition]]
id = "<machine>.<from>-><to>[.<qualifier>]"   # the naming law; unique; the diff anchor
machine = "task"
from = "backlog"                        # a state id in facets[0]
to = "ready"
lane = "standalone"                     # optional; feeds surface 2
actor = ["human", "attended-agent"]     # ACTORS — who may perform it at all
agent_may = "propose"                   # AGENT_MAY — read only when attended-agent is in actor
door = "one-way"                        # DOOR — consequences, never diffs
writes_unguarded_facets = []            # rule F2's escape hatch; each entry needs a `why` below
because = "the teaching sentence; displayed in the map's trailing column, never evaluated"

  [[transition.guard]]                  # >=0 rows; ALL must hold. CONJUNCTION ONLY.
  predicate = "record_present"          # from PREDICATES; a prose condition is unwritable
  args = { record = "YR-TASK-GATES" }
  why = "the sentence the refusal SPEAKS and the map's condition column prints"
  window = "since-store-change"         # optional; rejected on a store with no change_clock

  [[transition.post]]                   # >=1 row; what must be TRUE after. Re-read at close.
  predicate = "facet_is"
  args = { facet = "status", state = "ready" }

# ── invariants: act hygiene with NO state semantics. Named as the weaker tier it is. ─────────
# LOADER: an invariant whose guards reference facet_is/store_is is REJECTED — if it depends on
# state it is a transition guard and must live there. That rule is what stops this table from
# becoming the mechanism-scoped guard backdoor that lost the Reason rule in the first place.
[[invariant]]
id = "git.commit.trailer"
title = "an attended commit credits the authoring model"
tool = "Bash"
actor = ["attended-agent"]
door = "reversible"
authority = "AGENTS.md conventions"
does_not_cover = ["an editor-driven commit (the body is not visible pre-execution)",
                  "git commit --amend of a body written earlier",
                  "any porcelain wrapper"]

  [[invariant.guard]]
  predicate = "act_field_contains"
  args = { field = "message", literal = "Co-Authored-By:" }
  why = "the authoring model is credited in the commit body"

# LOADER: an [[invariant]] can never reach ENFORCEMENT "prevented", whatever its bindings.

# ═══════════════════ THE SEAM ════════════════════════════════════════════════════════════════
# Everything below is VENDOR-COUPLED. A port.* row may cite a neutral id; a neutral row may
# NEVER cite a port.* id. Loader-enforced, one direction. A port to a second harness rewrites
# this half only — and the load then RE-DERIVES every enforcement value above and FAILS on any
# coverage the new port cannot support. A port cannot silently lose coverage.

[port.transport.anthropic-claude-code]  # STANCE -> mechanism. Verified empirically this session.
event_pre = "PreToolUse"
event_close = "Stop"
refuse = { permissionDecision = "deny" }
escalate = { permissionDecision = "ask" }        # the native human escalation at a one-way door
advise = { hookSpecificOutput = "additionalContext" }   # the advisory stance, finally transported
observe = { permissionDecision = "defer" }
block_exit_code = 2
note = "any other non-zero exit is INVISIBLE and lets the call through; decisions go on stdout"

[[port.probe]]                          # the DECAY instrument
id = "gh.project.surface"
vendor = "github"
subject = "the `gh project` subcommand surface the board bindings match against"
fingerprint_cmd = "gh project --help"   # stdout, sha256'd
fingerprint = "sha256:9f2c..."          # recorded at last verification
verified_on = "2026-08-08"
recheck_days = 30
on_drift = "downgrade"                  # "downgrade" | "break" — never "ignore"

[[port.binding]]                        # an observed ACT -> a STORE and a VALUE. BY EFFECT.
id = "board.write.gh-cli"               # THERE IS NO `transition` KEY IN THIS TABLE.
vendor = "github"
observed_via = "anthropic-claude-code:PreToolUse"
tool = "Bash"
precision = "exact"                     # PRECISION; over-matching may never refuse
does_not_cover = ["argv assembled at runtime inside a script the hook never sees",
                  "a write issued by a process spawned before the hook fires"]
probe = "gh.project.surface"
verified_on = "2026-08-08"
recheck_days = 30
verify = "tests/process/verify_board_binding.sh"   # asserts the act still matches

  [port.binding.match]                  # typed selector over the NORMALIZED act. No raw regex.
  kind = "argv"                         # MATCH_KIND — there is no `substring`, no `regex` member
  program = "gh"
  subcommands = ["project", "item-edit"]

  [[port.binding.writes]]
  store = "board.status"
  write_path = "gh-cli"                 # the path on THAT store this binding covers (rule C)
  selects_when = { kind = "flag-equals", flag = "--field-id", source = "board_plumbing.status_field_id" }
  value = { kind = "option-id", flag = "--single-select-option-id", map = "board_plumbing.status_opt" }

  [[port.binding.writes]]
  store = "board.reason"
  write_path = "gh-cli"
  selects_when = { kind = "flag-equals", flag = "--field-id", source = "board_plumbing.reason_field_id" }
  value = { kind = "option-id", flag = "--single-select-option-id", map = "board_plumbing.reason_opt", clear_flag = "--clear", clear_to = "" }
```

## Migration this design requires (named, not assumed)

1. **`records.toml` gains a typed `emitted_by` column** on every row — a list of ACTORS values, beside today's prose `emitter`. Loader rule S needs it; without it, satisfiability is unenforceable. This is a small registry amendment and I name it as a dependency rather than pretending it exists.
2. **`records.toml`'s `[lanes]` table is DELETED**; `records.lanes()` delegates to `process.lanes()`. One authority.
3. **`tools/wall.py`'s `RULES` dict, `classify()`, `board_check()` and `promote_check()` are deleted** — the first is a hand-restated drift twin of the canon table, the last two are the second and third implementations of the `YR-BOARD-FLIP` / `YR-TASK-GATES` grammars.
4. **`tools/board_plumbing.py:_attended_wall`'s inline `l.startswith("YR-BOARD-FLIP:")` (line 145) is deleted.** Once `gh project item-edit` is a covered write path, the funnel needs no matcher of its own, and the stdlib-only invariant that forced the inline spelling stops applying. An agreement test asserts no `YR-` marker literal outside `textutil` / `check_trail` / `predicates`.

## Worked example

The four transitions, in the schema above. Every stanza was parsed with `tomllib` before it was written here.

## (a) Backlog -> Ready, standalone task

```toml
[[transition]]
id = "task.backlog->ready.standalone"
machine = "task"
from = "backlog"
to = "ready"
lane = "standalone"
actor = ["human", "attended-agent"]
agent_may = "propose"
door = "one-way"
because = "the standalone lane's human input gate: no governing design carries the approval, and promotion starts an autonomous build that opens a PR"

  [[transition.guard]]
  predicate = "record_present"
  args = { record = "YR-TASK-GATES" }
  why = "the standalone lane's review + fit gate; YR-PROMOTED never satisfies it"

  [[transition.post]]
  predicate = "facet_is"
  args = { facet = "status", state = "ready" }

  [[transition.post]]
  predicate = "record_present"
  args = { record = "YR-PROMOTED" }
```

**Derived, not authored.** `door = "one-way"` + `agent_may = "propose"` + guards TRUE => **escalate** => `permissionDecision: "ask"`. The agent prepares the gates record; the HUMAN answers the prompt. The per-task human promote stops being a memo in `attended-lane.md` and becomes a native transport. Rule D also bites here: had the author written `agent_may = "execute"` next to `door = "one-way"`, the model would not load.

**The load-bearing SILENCE.** There is no post on `reason`, and rule F2 makes that silence enforced rather than accidental: this transition does not guard on `reason`, so a post on `reason` is a LOAD ERROR unless declared in `writes_unguarded_facets`. *"The first must not clear a stale Reason"* is proved, not remembered.

**Satisfiability (rule S).** `YR-TASK-GATES.emitted_by = ["human", "attended-agent"]` and the transition's actors are the same, so S looks for a producing transition — and finds none, because the gates record is posted by a review act, not by this promote. Correct: S rejects only a transition walled by a record NO declared actor or predecessor can produce. Had the guard been a record `promote.sh` itself emits as part of this same act, S would REJECT the model — that is the `promote.sh` half-write defect, dead at load time.

## (b) Blocked -> Ready — the rule that had nowhere to live

```toml
[[transition]]
id = "task.blocked->ready.unblock"
machine = "task"
from = "in-progress"
to = "ready"
lane = "standalone"
actor = ["human", "attended-agent"]
agent_may = "execute"
door = "reversible"
because = "unblocking is the same board write as promotion and a DIFFERENT rule: the Reason that justified the block must not survive the unblock"

  [[transition.guard]]
  predicate = "facet_is"
  args = { facet = "reason", state = "blocked" }
  why = "this is the unblock; a clean In Progress -> Ready is a different row"

  [[transition.guard]]
  predicate = "record_present"
  args = { record = "YR-BOARD-FLIP" }
  why = "record-before-flip, typed"
  window = "since-store-change"

  [[transition.post]]
  predicate = "facet_is"
  args = { facet = "status", state = "ready" }

  [[transition.post]]
  predicate = "facet_is"
  args = { facet = "reason", state = "none" }
```

**Rule F1 fires.** The first guard reads `reason`, a non-primary facet, so a post disposing `reason` is REQUIRED. Delete the second post and `process.toml` does not load. *"The second must CLEAR a stale Reason"* is proved.

**Same mechanism, disjoint rules.** (a) and (b) share every binding — a `gh project item-edit` writing Status to Ready is the same call in both cases. The act table has no idea either transition exists: it resolves `board.status <- "Ready"` and the ENGINE reads the current state to pick the row. `window = "since-store-change"` uses `board.reason`'s declared `change_clock` so one old flip record cannot license every future flip; the loader rejects `window` on a clockless store.

**No wildcard.** The Minimalist needed `from = ["*"]` here because it had no way to make `blocked` a real thing. Rule P makes `blocked` a named state of the `reason` facet, so the row states a concrete Status precondition and surface 3 stops listing this transition as "next legal" for a Backlog task.

## (c) In Review -> Done via the merge evaluator — three rows, deliberately

```toml
[[transition]]
id = "pr.approved->merged.evaluator"
machine = "pr"
from = "approved"
to = "merged"
lane = "merge"
actor = ["machinery"]                   # NOT attended-agent. The categorical refusal is this word.
door = "one-way"
because = "the armed output gate; an attended hand-merge is refused because no actor class an attended session belongs to may perform this transition — no special 'categorical' concept is needed"

  [[transition.guard]]
  predicate = "store_is"
  args = { store = "manifest.auto_merge", value = "true" }
  why = "an unarmed repo keeps the human's click (the named transitional exception)"

  [[transition.guard]]
  predicate = "store_is"
  args = { store = "host.merge_sentinel", value = "clear" }
  why = "the host kill switch is not thrown"

  [[transition.guard]]
  predicate = "evaluator_pass"
  args = { evaluator = "merge" }
  why = "every merge condition holds, in the evaluator's own order with its own fail-closed semantics"

  [[transition.post]]
  predicate = "store_is"
  args = { store = "pr.merged", value = "true" }

  [[transition.post]]
  predicate = "record_present"
  args = { record = "YR-MERGE" }

[[transition]]
id = "task.in-review->done.native"
machine = "task"
from = "in-review"
to = "done"
lane = "merge"
actor = ["external-service"]            # GitHub's native close->Done automation
door = "one-way"
because = "we do not gate GitHub; the board move is detected, never prevented"

  [[transition.guard]]
  predicate = "store_is"
  args = { store = "pr.merged", value = "true" }
  why = "native close->Done follows the merge, never precedes it"

  [[transition.post]]
  predicate = "facet_is"
  args = { facet = "status", state = "done" }
```

Bindings for `pr.merged` — three doors, all resolving the same transition:

```toml
[[port.binding]]
id = "merge.gh-cli"
vendor = "github"
observed_via = "anthropic-claude-code:PreToolUse"
tool = "Bash"
precision = "exact"
does_not_cover = ["a wrapper script", "a merge queue", "gh alias set shortcuts"]
probe = "gh.pr.surface"
verified_on = "2026-08-08"
recheck_days = 30

  [port.binding.match]
  kind = "argv"
  program = "gh"
  subcommands = ["pr", "merge"]

  [[port.binding.writes]]
  store = "pr.merged"
  write_path = "gh-cli"
  value = { kind = "literal", literal = "true" }

[[port.binding]]
id = "merge.graphql"
vendor = "github"
observed_via = "anthropic-claude-code:PreToolUse"
tool = "Bash"
precision = "exact"
does_not_cover = ["a query supplied on stdin or via a heredoc, never present in argv",
                  "a non-gh HTTP client such as curl with a PAT"]
probe = "gh.api.surface"
verified_on = "2026-08-08"
recheck_days = 30

  [port.binding.match]
  kind = "graphql-mutation"
  mutations = ["mergePullRequest"]

  [[port.binding.writes]]
  store = "pr.merged"
  write_path = "graphql"
  value = { kind = "literal", literal = "true" }
```

**The honest shape.** `pr.merged`'s write paths are `gh-cli`, `graphql`, `rest`, `web-ui`. Three are bound live; `web-ui` is `observable = false` and names `detected_by = "YR-MERGE"`. So ENFORCEMENT derives **`partial`**, with `web-ui` plus both `does_not_cover` lists printed verbatim as open paths. `prevented` is unreachable here and the model provides no field in which to claim it. And the missing REST row is not an oversight anyone has to notice: rule C makes `rest` an uncovered observable path and the model does not load until it is written.

**Every hand-merge spelling refuses through one word.** An attended agent's `gh pr merge`, raw `mergePullRequest`, or `PUT /merge` each binds to `pr.merged <- "true"`, resolves `pr.approved->merged.evaluator`, and `"attended-agent" not in actor` => **refuse**, naming the sanctioned executor. The wall never needs to know what a merge command looks like in general — only what writes the store.

## (d) A vault design doc: draft -> active

```toml
[[transition]]
id = "design-doc.draft->active"
machine = "design-doc"
from = "draft"
to = "active"
lane = "design"
actor = ["human", "attended-agent"]
agent_may = "propose"
door = "one-way"
because = "the human input gate — what gets built; the standing approval under which the epic gate promotes slices mechanically"

  [[transition.guard]]
  predicate = "record_present"
  args = { record = "YR-DESIGN-REVIEW" }
  why = "the cold adversarial review, typed into the doc"

  [[transition.guard]]
  predicate = "record_present"
  args = { record = "YR-DESIGN-FIT" }
  why = "the architect's fit verdict at the spec-ready moment"

  [[transition.guard]]
  predicate = "record_absent"
  args = { record = "YR-OPEN-QUESTION" }
  why = "the airlock rule: an open question blocks the crossing"

  [[transition.post]]
  predicate = "facet_is"
  args = { facet = "status", state = "active" }

  [[transition.post]]
  predicate = "record_present"
  args = { record = "YR-ACCEPT" }
```

```toml
[[port.binding]]
id = "design.stamp.obsidian-mcp"
vendor = "obsidian"
observed_via = "anthropic-claude-code:PreToolUse"
tool = "mcp__obsidian__vault_patch"
precision = "exact"                     # structured input, key/value equality — no text anywhere
does_not_cover = ["a patch replacing the whole frontmatter block"]
probe = "obsidian.mcp.surface"
verified_on = "2026-08-08"
recheck_days = 60

  [port.binding.match]
  kind = "mcp-tool"
  arg_equals = { targetType = "frontmatter", target = "status" }

  [[port.binding.writes]]
  store = "doc.frontmatter.status"
  write_path = "mcp-patch"
  value = { kind = "frontmatter-value", arg = "content" }

[[port.binding]]
id = "design.stamp.fs-write"
vendor = "obsidian"
observed_via = "anthropic-claude-code:PreToolUse"
tool = "Write|Edit"
precision = "over-matching"             # -> this binding can NEVER refuse; it advises
over_matches = "every vault .md write, most of which are not a lifecycle stamp; it cannot read the frontmatter it is about to write, so it cannot confirm the effect"
does_not_cover = ["MultiEdit until its own row is added", "a symlinked path", "a path built at runtime"]
probe = "none"
verified_on = "2026-08-08"
recheck_days = 180

  [port.binding.match]
  kind = "path-write"
  path_under = "$YR_VAULT_ROOT"
  path_glob = "**/*.md"

  [[port.binding.writes]]
  store = "doc.frontmatter.status"
  write_path = "fs"
  value = { kind = "frontmatter-value", arg = "content" }
```

**Where `advise` finally comes from.** The FS binding over-matches by construction, so the derivation degrades its refusal to `advise` — `hookSpecificOutput.additionalContext`, injected next to the tool result without blocking. This is the advisory stance that previously had no mechanism at all and therefore collapsed into refuse-or-be-silent. It is not authored: it falls out of a binding honestly declaring that it cannot confirm the effect it matches.

**Rule R at work.** All three guard records resolve in `records.toml` AND their rows declare `surfaces = ["vault-doc"]`, so the read is routed by the registry. The predicate takes no surface argument, so a guard that looks for `YR-DESIGN-FIT` on an issue trail is unspellable.

## Compilation

All four compile through `tools/process.py compile <surface>` from `process.toml` + `records.toml`, after loader rules P/F1/F2/D/A/C/C2/R/S/V pass. Each artifact carries `GENERATED from process.toml v<version> sha256:<hash> — never hand-edit`; the artifacts are **committed**, so a PR diff shows both the model change and its consequences, and `process.py check --drift` recompiles and fails on any difference. Hand-authoring is mechanically impossible to keep.

One shared helper, the **only** place a predicate becomes prose — `render(guard)`:

| predicate | rendered as |
|---|---|
| `record_present("X")` | `<guard.why> — the \`X\` record (records.toml: marker \`<row.marker>\`, mode \`<row.mode>\`, fields <row.fields>, on <row.surfaces>)` |
| `record_absent("X")` | `<why> — no \`X\` line on <row.surfaces>` |
| `facet_is(f, s)` | `<why> — the \`f\` facet reads \`<state.value>\` (<store.kind> <store.location>)` |
| `store_is(st, v)` | `<why> — \`st\` reads \`v\` (<store.kind> <store.location>)` |
| `evaluator_pass(e)` | `<why> — the \`e\` evaluator passes (<evaluator.argv>)` |
| `act_field_contains(f,l)` | `<why> — the act's \`f\` carries \`l\`` |

The `why` teaches; the parenthetical is read from the registry row at compile time and therefore cannot drift from the record it cites. This is the graft: the Long Game's `why` fixes the Minimalist's machine-prose condition column, and the Minimalist's registry rendering fixes the Long Game's map never naming `YR-TASK-GATES`.

---

## 1 — The walled-act map (`build/walled-acts.md`, spliced into `attended-lane.md` between generated markers). FULLY GENERATED.

```
rows = []
for b in port.binding:
  for w in b.writes:
    store = stores[w.store]
    # TIER 2 — store permission, no transition needed
    for cls in ACTORS - store.writable_by:
      rows += Row(tier="store-permission", act=b.id, effect=f"{store.id} <- (any)",
                  condition=f"writable_by = {store.writable_by}", stance="refuse",
                  enforcement=ENFORCEMENT_for_store(store))
    # TIER 1 — every transition whose posts write this store
    for t in transitions_writing(store):
      for caller in ACTORS:
        rows += Row(tier="transition", act=b.id,
                    effect=f"{store.id} <- {value_of(t.to, store)}",
                    transition=f"{t.machine}: {t.from} -> {t.to}",
                    caller=caller,
                    condition=" AND ".join(render(g) for g in t.guard),
                    stance=STANCE(caller, t, guards=TRUE, binding=b),
                    stance_on_fail=STANCE(caller, t, guards=FALSE, binding=b),
                    door=t.door, enforcement=ENFORCEMENT(t),
                    open_paths=OPEN(t), because=t.because)
for inv in invariant:  rows += Row(tier="conduct", ...)   # never reaches "prevented"
```

Fields read: `store.{id,writable_by,write_path[]}`, `transition.{machine,from,to,actor,agent_may,door,guard,post,because}`, `binding.{id,precision,does_not_cover,probe,verified_on}`, plus the `records.toml` rows named by record guards. **Both stance columns are printed** (guards-TRUE and guards-FALSE) so a reader never has to evaluate a table living in code — the judge's complaint against the Adversary, fixed. Every `partial` row prints its open paths verbatim: `open: <write_path.how> (detected by <record>)` plus each binding's `does_not_cover`. The map can no longer read as complete when it is not.

Today's 8 hand-written rows become ~20 generated ones, and the growth is the point: one mechanism with two transitions prints two rows, which is exactly the distinction the shipped table could not express.

## 2 — The detector's lane mandates (`build/lanes.toml`). FULLY GENERATED. **Traced as code against the shipped registry.**

```python
MANDATE, FORBID = "record_present", "record_absent"

def on_course(model, t):
    """A transition is on its lane's course unless it guards a NON-PRIMARY facet — such a guard
    makes it a conditional detour (the unblock applies only to a task that was blocked)."""
    p = primary_facet(model, t.machine)
    return not any(g.predicate == "facet_is" and g.args["facet"] != p for g in t.guard)

def lanes(model):
    mandate, forbid = {}, {}
    for t in model.transition:
        if not t.lane or not on_course(model, t): continue
        for p in t.guard + t.post:
            if   p.predicate == MANDATE: mandate.setdefault(t.lane, set()).add(p.args["record"])
            elif p.predicate == FORBID:  forbid.setdefault(t.lane, set()).add(p.args["record"])
    return mandate, forbid
```

I ran this against `records.toml` with a stand-in transition set covering all four declared lanes:

```
                today (hand-listed)                    derived (compiled)
close       ['YR-ROUND-RECORD','YR-SHIP-WALK']    identical
design      ['YR-ACCEPT','YR-DESIGN-FIT','YR-DESIGN-REVIEW']   identical
epic        ['YR-EPIC-APPROVAL']                  +['YR-AUTO-PROMOTED']
standalone  ['YR-TASK-GATES']                     +['YR-PROMOTED']
must-not-carry: {'epic': ['YR-OPEN-QUESTION']}
unregistered names in derived lanes: none
```

Two lanes reproduce byte-identically. Two gain the funnel's own emission record — a **strict improvement**, not drift: `records.toml` says `YR-PROMOTED` lands "by construction" at `promote.sh:68`, so a standalone trail without it means the flip happened outside the funnel, which is precisely what a detector exists to find. The hand-listed table simply under-demanded.

Running the prototype also caught a real inversion in my first draft: `record_absent` guards were becoming presence mandates, which would have made the epic lane demand `YR-OPEN-QUESTION` — the exact opposite of the airlock rule. They now compile to a separate must-not-carry list. Neither rival proposal's compiler distinguishes the two.

`tools/check_trail.py` changes by one line — `records.lanes(reg)` at `:115` becomes `process.lanes(model)` — and its `_marker_present` / `_missing_fields` core (which is also `record_present`'s implementation) is untouched. `records.toml`'s `[lanes]` table and `records.py`'s lane validator are deleted. New sharper unit: `check_trail.py --transition task.blocked->ready.unblock` checks exactly that row's guards + posts, answering the over-demand a lane union creates by construction.

## 3 — The session-start slice. **GENERATED except the router pointers** (imported from `SKILL.md`, exactly as `compile_slice.py` does today).

*Static half (`build/slice-static.md`, cacheable):*
- **Part 1 — the machines.** Per machine, per facet: each state with its store and its LITERAL stored value. The belief-killer, rendered.
- **Part 2 — the walled-act map**, surface 1 verbatim, both stance columns.
- **Part 3 — the honesty block.** Per transition: `ENFORCEMENT(t)` and, when not `prevented`, the open paths verbatim. An agent is told what is NOT walled, so it never reads silence as permission. `[boundary].caller_trust` printed verbatim: *this boundary is declared, not proven.*
- **Part 4 — the router rows** from `SKILL.md`. The one part not derived from this model, named honestly.

*Position half (composed at delivery by `hooks/deliver.sh`, never cached):*
1. Resolve scope from `cwd` + `[boundary]` + the branch name (`task/<n>-<slug>`).
2. Per facet, read the store via `source` -> current state. Rule P guarantees exactly one match. Unresolvable renders `position: UNRESOLVED (board.status unreadable: <reason>)` — never omitted, never guessed.
3. `legal = [t for t in transitions if t.machine == m and t.from == current]`.
4. Per legal transition: `-> {t.to} · actor {t.actor} · door {t.door} · stance {STANCE(caller,t,TRUE,None)}`, then one line per guard rendered by `render()`, prefixed from a LIVE read: `ok` / `missing: <what>` / `unknown: <what could not be read>`. For `evaluator_pass("merge")` the detail is the evaluator's own failed-condition token — *"still needs: freshness"* — without this model knowing what freshness is.
5. **The human's checkpoints — DERIVED, not authored:** `[t for t in legal if "human" in t.actor and t.agent_may != "execute"]`, each marked and each showing that `escalate` (an `ask`) is the available transport. Today this list is hand-written in `attended-lane.md`; it becomes a projection of two fields.
6. **Decay banner:** any transition reachable from here whose ENFORCEMENT is degraded prints `COVERAGE DEGRADED: <store>.<path> — binding <id> <decay> since <date>`.

`MAX_BYTES` and the fail-loud-past-the-bound rule carry over unchanged. Delivery stays loud-non-blocking: the position half is best-effort with a hard per-source timeout and degrades to the static half plus `UNRESOLVED`, never delaying session start.

## 4 — The close report. FULLY GENERATED, with declared blind spots.

Input: the session's journal (`[observability].journal`), one row per decision `{ts, transition_id|invariant_id, binding_id, scope, stance, caller}`, written by the wrapper AFTER `decide()` returned.

```
for tid in distinct(journal.transition_id) where stance in ("observe", "escalate-approved"):
    t = model[tid]
    failed = [render(p) + " — " + detail for p in t.post if evaluate(p, scope) is not TRUE]
    emit f"{tid}: postconditions {'LEFT BEHIND' if not failed else 'MISSING: ' + '; '.join(failed)}"

# blind spots — always printed, derived from rows the model already carries
for store touched this session:
    for path in store.write_path where not live(path):
        emit f"NOT OBSERVED: {path.how} — detected only by {path.detected_by} via check_trail.py"

# the maintenance-tail alarm, from having both bindings and posts on the same row
for t in transitions where ENFORCEMENT(t) in ("partial", "detected"):
    if all record posts of t hold NOW and t not in journal:
        emit f"BINDING GAP OBSERVED: {t.id} happened this session and no binding matched it — {gaps}"

counts = { refusals: stance == "refuse",
           records-demanded: distinct record guards that evaluated FALSE,
           detector-findings: check_trail over the compiled lanes for this scope,
           escalations: stance == "escalate" }     # exactly YR-ROUND-RECORD's four fields
```

Fields read: `transition.post`, `store.write_path`, `binding.does_not_cover`, plus `records.toml`'s `YR-ROUND-RECORD` row for the emitted record's own grammar. Two properties the shipped close check got backwards: it now tracks **mandated traces (postconditions)** rather than its own refusals, and **an unreadable journal renders every line `UNKNOWN (journal unreadable: <reason>)`, never `ok`** — a report that cannot see is never a clean report.

**Stop REPORTS; transitions GATE.** The report rides `hookSpecificOutput.additionalContext`. `{"decision":"block"}` is used only for the once-then-override missing-postcondition refusal, and it is an acknowledgment gate, not a transition gate — the transitions were gated at PreToolUse.

## 5 — `build/conformance.json` (the fifth artifact, beyond the four asked for)

`process.py compile conformance` emits, from rows that already exist: (i) per binding, a vector PAIR asserting `decide()` is byte-identical with the journal path writable and unwritable; (ii) per guard, a vector asserting an unreadable source yields UNKNOWN and disposes as `refuse`, never a pass; (iii) per act-matcher, a vector asserting the funnel spelling and the raw spelling reach the SAME transition. The pytest suite consumes it. This is how the schema's promises reach the code instead of staying claims — and it is the probe nobody generated last time, which is why six of eleven shapes disagreed unnoticed.

## What does NOT generate, named plainly

The `because` teaching sentence and each guard's `why`; the router pointer rows in slice part 4; the human's prose close summary; `over_matches` and `does_not_cover` prose; and the *correctness* of a source's implementation. `process.py surfaces --diff` shows a reviewer what a model diff DOES to all four surfaces, which is the artifact a gate reviewer actually needs.

## Predicates

**Verdict on the question asked: yes, a closed vocabulary is right — but closedness is not what does the work.** A vocabulary of fifteen predicates would be fifteen new implementations, which is the shipped disease wearing a registry's clothes. Two rules make it stick, and the second is the one the shipped tree actually needed:

> **ADMISSION.** A new predicate is admissible only if (i) no implementation of it exists anywhere in the tree, and (ii) at least two rows need it. Otherwise: delegate through `[[evaluator]]`, or express it as a store. Adding one is a `[model].version` bump plus an `[[amendment]]` — closed, not frozen; growth has a price and a paper trail.
>
> **PURITY.** Predicates are **pure functions over a fetched context**. All I/O lives in `[[source]]` fetchers. A predicate module that imports `subprocess`, `socket`, `urllib`, or `pathlib.Path.read_text` is rejected by an import-level guard in the test suite.

Purity is the root-cause fix. In the shipped tree `wall._trail_has` (`:205`), `wall.board_check` (`:329`) and `wall.promote_check` (`:381`) each FETCH and JUDGE — and each therefore grew its own judge, disagreeing in 6 of 11 probed shapes in both directions. A call site with nothing to parse until it asks a source has no way to re-implement quietly. Mandating "one implementation" without removing the fetch would have left the motive intact.

## The six. Each returns tri-state: `TRUE | FALSE | UNKNOWN(reason)`. `Result` implements no `__bool__`.

**`facet_is(facet, state)`**
- Args validated at load: `facet` in the transition's machine, `state` a declared state of that facet.
- Reads: the facet's store via `store.read`, then maps the raw value back through the store's `values` to a state id.
- UNKNOWN: store unreadable; a value outside `values` (`unknown_value_policy = "unknown"` — never coerced to the nearest legal option); the scope key not extractable from the act.
- Used by rules F1/F2 as the marker of "this transition disposes facet X".

**`store_is(store, value)`** — for stores that are not machine facets (`manifest.auto_merge`, `host.merge_sentinel`, `pr.merged`).
- Reads: that store's `read` source; `manifest-key` reads the base ref's tip at decision time, per the merge evaluator's own contract.
- UNKNOWN: read fails, times out, TOML unparseable, or the value is outside `values`.

**`record_present(record)`**
- One argument, validated at load against `records.toml` (rule R). **Takes no surface argument** — the registry row's `surfaces` ROUTES the read, so a caller cannot look in the wrong place. This is the cheapest structural device in the design and it comes from the Minimalist.
- Implementation: `check_trail._marker_present` + `check_trail._missing_fields`, **imported, not re-spelled**. One function, four callers (detector, wall, slice, close report). The existing rule that a record's fields must be complete within ONE text (never pooled across comments) comes along for free.
- Optional `window = "since-store-change"`: the record must be newer than the store's `change_clock`. The loader REJECTS `window` on a clockless store, so recency cannot be faked where it cannot be checked.
- UNKNOWN: the surface cannot be fetched, `gh` non-zero, timeout, or the scope key is not extractable. **Never FALSE.**

**`record_absent(record)`** — the airlock shape (`YR-OPEN-QUESTION` must not ride a filed epic).
- Same reader, inverted result, and the load-bearing part: **UNKNOWN stays UNKNOWN.** This is why there is no `not` combinator — `not UNKNOWN` is the fail-open trapdoor, and a negation operator hands it to every author.

**`evaluator_pass(evaluator)`** — the delegation seam.
- Runs the declared `argv` with `{scope.*}` substituted, bounded by `timeout_s`.
- Contract: exit 0 -> TRUE. Exit 1 -> FALSE with stdout's first line as the failed-condition token (which is what lets the slice say "still needs: freshness"). Any other exit code, a timeout, an `OSError`, or an empty token on exit 1 -> UNKNOWN. Indeterminate is never success — the merge evaluator's own rule, inherited rather than restated.

**`act_field_contains(field, literal)`** — invariants only; pure over the normalized act, no I/O.
- UNKNOWN when the field is not visible pre-execution (an editor-driven commit body). The shipped `_classify_commit` already discovered this case; here it is a typed UNKNOWN rather than a `return None`.

## Disposition — one table, one place in the code

| | evaluable FALSE | UNKNOWN |
|---|---|---|
| exact binding | **refuse**, naming the failed guard's `why` and its rendered citation | **refuse**, naming *what could not be read* |
| over-matching binding | **advise** (`additionalContext`) | **advise**, saying it could not evaluate |

There is no row producing a pass, and there is no `on_indeterminate` field to author. *"Infrastructure failure is not condition failure"* becomes one column of one table rather than a sentence repeated at every site — and the refusal TEXT differs between columns, so a human reading a wall message can always tell "your record is missing" from "I could not reach GitHub".

## Parse and validation

Guards are `[[transition.guard]]` sub-tables with a `predicate` from the closed tuple and an `args` inline table — **no embedded call-string syntax, so no hand-rolled parser** (a simplification over the Minimalist's `record_present("X")` strings and their ~12-line grammar). Arity and every argument are resolved at load against `records.toml` / `machine` / `state` / `store` / `evaluator`. **A typo is a load error, not a silently-false guard.** That property matters more than the syntax.

## Deliberately not added

`not_`, `any_`, `older_than`, `count_ge`, and any boolean combinator. Guards are AND-only, in declaration order, first non-TRUE naming the refusal — which also preserves `merge_shadow`'s `SHADOW_ORDER` contract as data. A genuine OR is two transition rows, which is usually a *correction*: two ways to reach a state are two transitions with different postconditions, exactly as `Backlog->Ready` and `Blocked->Ready` separated. `shadow_complete` is a counting condition and it lives inside the evaluator, where its one implementation already is.

## Bindings

**The principle: an act binds to a STORE and a VALUE. The transition is resolved at runtime by reading where the machine actually is.** `[[port.binding]]` has no `transition` key and strict unknown-key rejection means one cannot be improvised. Binding a wall to a specific transition is not expressible — which is the whole answer to "guards bind to transitions, not mechanisms": one mechanism reaches many transitions, and which one you get depends on the current state.

## The normalized act

The wall never sees a command string. A per-tool normalizer (`tools/acts.py`, vendor-coupled) produces a typed record; selectors match *that*:

```python
Act = {
  "tool": "Bash" | "Write" | "Edit" | "mcp__obsidian__vault_patch" | ...,
  "segments": [Seg, ...],        # a pipeline / && / ; / newline / $() chain -> N segments, ALL matched
  "program": "gh",               # basename(argv[0]), after ONE declared unwrap pass for
                                 # python3|python|uv|env|sh -c|bash -c
  "subcommands": ["project", "item-edit"],   # ordered leading non-flag tokens
  "flags": {"--id": "PVTI_...", "--field-id": "..."},
  "operands": [...],
  "path": "/abs/resolved/path",  # Write/Edit: symlinks followed, ".." collapsed
  "fields": {...},               # MCP tool_input, verbatim
  "unparsed": False,             # shlex failure — a DECISION INPUT, never a hole
}
```

Two consequences worth naming. **`cmd | tail` and `a && b` produce multiple segments, each matched independently** — the shipped wall's `[^|;&]*` regex silently stopped at the first pipe. And **an unparseable command is not an unmatched command**: `unparsed = True` matches any binding declaring `unparsed_matches = true` for a guarded store, disposing per the normal table. Unreadability refuses; it does not fall through.

## The decision path, in order. Every step total; none can raise.

1. **Boundary first.** Resolve `cwd` and the act's target path against `[boundary]`. Out of scope -> `observe`, exit 0, silence, **no I/O at all**. A personal repo never hears from this lane.
2. **Classify (pure, offline).** Walk `[[port.binding]]` rows whose `tool` matches, applying `match` through the single implementation for its MATCH_KIND. No match -> `observe`, exit 0. An unwalled Bash call costs one `shlex` parse.
3. **Resolve the effect.** For each `binding.writes` probe: `selects_when` decides whether this call touches that store; `value` resolves the target value through its VALUE_KIND extractor. Extraction returns UNKNOWN -> the **strictest stance among all transitions that could write this store**. An unreadable argument refuses; it never falls through.
4. **Store-permission tier (no state read needed).** Caller class not in `store.writable_by` -> **refuse**, naming the store and its permitted classes. This is how `git.ref.protected` and `manifest.auto_merge` become categorical without a fake state machine over SHAs.
5. **Resolve the transition.** Read the machine's facets via their stores -> current state (rule P guarantees exactly one). Select the transition whose `from` is the current primary state and whose `to` contains the resolved target value. No such transition -> refuse: *"no lawful transition from `<current>` writes `<store>` to `<value>`"*. Current state unreadable -> all candidates live, **strictest stance among them**, naming the store it could not read.
6. **Evaluate guards**, in declaration order, tri-state.
7. **Dispose** per the derivation. The reason string is GENERATED: binding label, resolved transition, the first non-TRUE guard rendered by `render()`, and `t.because`. There is no `RULES` dict — the hand-restated drift twin the review flagged has no home. The model never emits `allow`: it will not override the user's own permission settings.
8. **Then, and only then, observe.** `sys.stdout.write(json); flush()` happens BEFORE any logging; the journal write is `try: ... except BaseException: pass`; and `tools/process.py`'s decision module **does not import** the journal module — an import-graph test asserts it, and `build/conformance.json` asserts byte-identical decisions with the journal path read-only. Bookkeeping physically cannot reach the decision, and the claim is tested behaviourally rather than argued.

## Matchers: closed, structural, and the shipped inversion is unspellable

`MATCH_KIND` has **no `substring` and no `regex` member.** `contains("board_plumbing.py")` — matching the lawful, self-checking door — cannot be typed.

- **`argv`** — per segment, `program` + ordered `subcommands` + required `flags`, i.e. the program's own CLI grammar. `arg_contains` (tokens inside a SINGLE argument's value) is the weakest form, reserved for raw mutation names, and always forces `precision = "over-matching"`.
- **`graphql-mutation`** — parses the query out of `-f query=` / `--field` and matches the **mutation name**, not the text around it.
- **`path-write`** — `Write`/`Edit` by resolved `path_under` / `path_glob` / `path_suffix`. A path is a structural fact about which bytes change; no text matching at all.
- **`shell-redirect`** — `tee` / `cp` / `sed -i` / `dd` / `>` / `>>` onto a guarded path. The shipped wall left this wide open.
- **`git-refspec`** — resolves the push TARGET by asking git (`git rev-parse --abbrev-ref`, `git symbolic-ref`), never by reading the command text. The shipped wall's branch-blindness — inferring "this is my own task branch" from a string at `wall.py:130-135` — is not expressible, because the extractor's input is the repository, not the argv.
- **`mcp-tool`** — tool name plus argument-path equality. Structured input, no spelling variance.

**The funnel needs no special case.** `tools/board_plumbing.py set-field` shells out to `gh project item-edit`, so it is covered by the `gh-cli` binding like every other caller — one classification, both doors, judged by the SAME guards. The lawful path passes when the record is there; the bypass is caught by the same rule. The shipped inversion is not a bug this design fixes; it is a shape this design cannot hold.

## How a binding declares its own completeness

Not by claiming a mode — modes are computed. Three levels compose:

| level | field | meaning |
|---|---|---|
| `[[store.write_path]]` | `observable` | is this path visible to the transport at all? `false` -> automatically an open path, and rule C2 requires `detected_by` or `undetectable = true` with a reason |
| `[[port.binding]]` | `precision` | `exact` (structural match on the program's own grammar or on structured input) vs `over-matching` (fires on acts it cannot confirm) — an over-matching binding **may never refuse** |
| `[[port.binding]]` | `does_not_cover` | **required non-empty.** You must write down at least one way around your own wall or the model fails to load. Honesty costs one line; dishonesty requires inventing a false one |

Then **rule C**: a `guarded = true` store with an `observable = true` write path that no binding covers is a **load error naming the store and the path**. The missing raw-GraphQL row is a build failure, not an invisible hole. And ENFORCEMENT is derived from coverage — **there is no field in which to type `prevented`.** In the whole worked model exactly one transition can earn it, and only because GitHub branch protection is server-side.

## The maintenance tail, mechanized on two clocks

Prevention rots; detection does not. The model encodes that asymmetry permanently — `detected_by` has **no decay clock**, because a trail either carries its record or it does not, regardless of how the write was spelled.

- **Probes.** Each binding names a `[[port.probe]]` fingerprinting the third-party surface (`gh project --help`, sha256'd), a `verified_on`, a `recheck_days`, and a runnable `verify`. `process.py decay` (run by the epic-gate sweep and the debt census) recomputes. Drift -> binding not live -> coverage recomputed -> ENFORCEMENT downgrades -> `build/walled-acts.md` regenerates -> `check --drift` fails -> and the **delivered slice prints `COVERAGE DEGRADED` at the next session start, before anyone edits the file**. Nobody has to be watching.
- **The gap alarm.** The close report emits `BINDING GAP OBSERVED` when a transition's record posts hold on the trail but no binding fired this session — detection noticing that prevention stopped matching. Zero new fields: it falls out of having both bindings and posts on the same row.

Probes catch the vendor surface changing. The gap alarm catches the wall silently ceasing to match. Neither alone is sufficient; together they cover the two ways a binding rots.

## Grafted

- **Per-store `[[store.write_path]]` enumeration with an `observable` flag, plus loader rule C: a guarded store with an observable write path that no live binding covers is a LOAD ERROR naming the store and the path.** (from THE ADVERSARY) — This is the direct patch for the base's single worst hole. THE MINIMALIST's `prevented <=> every non-funnel binding is complete` is satisfied vacuously by a transition that declares only its funnel — delete two stanzas from its own worked example (c) and the map asserts prevention over an open path. Making coverage an obligation of the STORE rather than a choice of the binding author turns the missing raw-GraphQL row from an unwatched hole into a build failure. Both judges who scored the base highest still flagged this as the graft it needed.
- **Stance and enforcement DERIVED with no field to author, and `does_not_cover` required non-empty on every binding.** (from THE ADVERSARY) — The base leaves `defer` in an authorable `stance` vocabulary — a one-word fail-open wall, which its own tradeoffs concede ('a too-lenient stance will pass every check in this document'). Removing the field means shipping a fail-open wall requires first mislabelling `door`, a semantically loaded word sitting next to `to` in the diff. I modified the derivation: the Adversary's table maps reversible+execute+guards-FALSE to `advise`, which would make record-before-flip advisory for the unblock, against the canon. Here guards-FALSE is always refuse and `advise` is reachable only from a binding declaring itself over-matching.
- **The one-way-door rule: `door = "one-way"` forbids `agent_may = "execute"`.** (from THE ADVERSARY (door concept) — the rule itself is this synthesis's) — In the Adversary's design `door` only selects a row of the stance table; once guards-FALSE always refuses, that job disappears and `door` would be decoration. Repurposed, it does the strongest structural work in the model: it makes the escalation valve MANDATORY at every one-way door rather than optional, which is how `ask` — the transport the canon called for and the shipped code never implemented — becomes unavoidable instead of remembered.
- **Loader rules F1/F2: a guard on a non-primary facet REQUIRES a post disposing that facet; a post on an unguarded non-primary facet is FORBIDDEN unless declared with a `why`.** (from THE LONG GAME (F1) + THE ADVERSARY's C2 intent (F2), reformulated) — The Adversary's C2 proves both halves of the brief's flagship constraint with subset math over from/to cell sets — correct, and something no author will re-derive at 2am. F1 is the same kill in one sentence. F2 is the inverse half the Long Game lacked entirely, which the Adversary got from `|T_S| == 1 => effect FORBIDDEN`. Together: omit the Reason clear on the unblock and the model does not load; ADD one to the fresh Backlog promote and the model also does not load.
- **Per-facet partition (rule P) instead of the Adversary's C1 partition of the full store product.** (from THE ADVERSARY, deliberately weakened) — C1 demands every Status x Reason cell (5x3 = 15) be named before the file loads, scaling multiplicatively with facets — judge 3's single largest authoring objection, and under pressure an author invents a catch-all state, keeping the ceremony and losing the guarantee. Per-facet is linear, achieves the same kill (`reason = ""` becomes the named state `none`, so no state's meaning is ambiguous), and removes the base's `from = ["*"]` wildcard, which its author called 'easy to overuse'.
- **A `why` string on every guard row, rendered as the refusal sentence AND the map's condition column, concatenated with the predicate's registry-derived citation.** (from THE LONG GAME (`why`) + THE MINIMALIST (`render`)) — Neither alone works. The Long Game's map prints only `why`, so it never names YR-TASK-GATES and goes stale when the record is renamed. The Minimalist's `render()` is accurate machine prose that teaches nothing, and its per-transition `note` is display-only and never reaches the refusal text. Concatenating them gives a refusal a human learns from and a citation that cannot drift from the row it names.
- **Predicates as pure functions over `[[source]]` fetchers, with an import-level guard rejecting a predicate module that touches the network or filesystem.** (from THE LONG GAME) — The correct root cause of one-grammar-three-implementations, and neither rival has it. In the shipped tree `_trail_has` (:205), `board_check` (:329) and `promote_check` (:381) each fetch AND judge, which is exactly why each grew its own judge. Mandating 'one implementation' without removing the fetch leaves the motive intact; a call site with nothing to parse until it asks a source cannot re-implement quietly. It also makes the tri-state cheap to test, since a source can be failed in a fixture.
- **`[[invariant]]` as a typed third tier for mechanism-hygiene rules, with the loader rule that an invariant referencing state predicates is REJECTED.** (from THE LONG GAME) — The base names 'pure mechanism rules' as the largest honest hole in its design and explicitly refuses to invent a home, fearing it re-creates the mechanism-scoped guard table that lost the Reason rule. The Long Game's load rule dissolves that fear in one sentence: an invariant that touches state is a load error, so the table structurally cannot absorb transition guards. Without it, 2 of the 8 shipped walled rows (commit trailer, off-table vault write) become inexpressible — a 25% functional regression against the surface being replaced.
- **Store-permission tier via `[[store]].writable_by`, evaluated before any state read.** (from THE ADVERSARY) — Makes `push main` and an agent-initiated arming edit categorical without inventing a fake state machine over SHAs or over a manifest key. One line per store, and it fills two more of the eight walled rows the base could not reach.
- **Decay probes: `[[port.probe]]` fingerprinting a vendor surface, with `verified_on` / `recheck_days` / `on_drift`, driving automatic coverage downgrade into the map, the drift check, AND a COVERAGE DEGRADED banner in the next session's slice.** (from THE LONG GAME) — The only mechanized answer to the brief's maintenance-tail constraint — 'each new subcommand silently widens the hole with nobody watching'. The base's `gap` strings are static prose that a `gh` rename does not touch; the Adversary only ages a server-side chokepoint. I paired it with the base's own BINDING GAP OBSERVED alarm because they catch different rots: probes catch the surface changing, the alarm catches the wall silently ceasing to match.
- **The `port.` prefix with a loader-enforced one-way reference rule (vendor rows may cite neutral ids; neutral rows may never cite a port id).** (from THE LONG GAME) — A purely lexical seam — no new file, no new vocabulary, visible in every diff, a few lines of loader code. It marks which half of the model is a bet on Claude Code hooks. The base mixes `tool = "Bash"` and `mcp__obsidian__vault_patch` directly into transition rows with nothing distinguishing the durable from the vendor-coupled.
- **`[[amendment]]` rows (version, kind, touches, reason, review, who) plus `process.py surfaces --diff` showing what a model diff DOES to the four compiled surfaces.** (from THE LONG GAME) — The strongest answer anyone gave to 'the model is gate-touching and must be reviewable by a human reading a diff'. A diff of a large TOML table is not self-interpreting. I dropped the Long Game's per-diff mandatory version bump enforced by an advisory checker — that is ceremony that gets skipped on a Friday and then reads as a lie in the file's own history — and kept the amendment row plus the consequences diff, backed by the base's committed hash-stamped artifacts so the reviewer sees both in one PR.
- **Generated conformance vectors as a compiled artifact: per binding, a pair asserting `decide()` is byte-identical with the journal writable and unwritable; per guard, a vector asserting an unreadable source disposes as refuse, never a pass.** (from THE ADVERSARY and THE LONG GAME (both proposed it)) — Strictly stronger than the base's import-graph test, which would not catch an exception raised inside a sink the wrapper invokes. It is also the probe nobody generated last time — which is precisely why six of eleven shapes disagreed unnoticed. Generated from rows that already exist, so it costs no authoring.
- **The `[[evaluator]]` delegation seam with its exit-code contract, plus the predicate admission rule.** (from THE MINIMALIST (kept from the base, against both rivals)) — Stated as a graft-refusal because it is load-bearing: both rivals restate merge_shadow.py's six-to-eight conditions as guard rows on the very transition whose executor IS merge_shadow.py. The implementation stays single via `delegates_to`, but the condition SET and ORDER then live in two authorities and drift the day a ninth condition lands. `evaluator_pass("merge")` plus a display-only `conditions_display` list is the maintenance-correct answer, and the failed-condition token is what lets the slice say 'still needs: freshness' without this model knowing what freshness is.
- **Lane mandates as the union of record predicates over guards AND posts, restricted to on-course transitions, with `record_absent` routed to a separate must-not-carry list.** (from THE MINIMALIST (union) — the on-course filter and the absent/present split are this synthesis's) — Stated as a graft-refusal because adopting either rival's effects-only rule would be a silent catastrophe: traced as code, it compiles the `design` lane EMPTY (their draft->active transition has no record effect; REVIEW and FIT are guards) and drops YR-TASK-GATES from `standalone`. Guard records are exactly the records emitted by human acts that no store-backed state machine can model as a transition. I added the on-course filter (a transition guarding a non-primary facet is a conditional detour) to answer the over-demand the union creates, and running the prototype caught that `record_absent` guards were becoming presence mandates — which would have made the epic lane demand YR-OPEN-QUESTION, the exact inverse of the airlock rule. Neither rival's compiler distinguishes the two.

## Honest limits

- PREVENTION OVER BASH REMAINS INCOMPLETE, AND ALWAYS WILL BE. Canonicalised argv matching with per-segment walking and one declared interpreter-unwrap pass is a real improvement over a regex on a raw line, but `curl` with a PAT, an SDK, a base64'd command, a heredoc-supplied GraphQL query, or a runtime-assembled argv escape every matcher in the vocabulary. What the model changes is that this can no longer be HIDDEN: `does_not_cover` is required non-empty, unobservable paths auto-list, and ENFORCEMENT has no field in which to claim `prevented`. The ceiling is declared and dated, not removed.
- THE CALLER CLASS IS DECLARED, NOT PROVEN. An agent that exports `YR_CALLER=machinery` walks out of every transition and store-permission refusal. `caller_trust = "declared"` is printed verbatim in every compiled surface rather than buried in a footnote, and the mitigation is asymmetric: the escape leaves no record while every lawful path does, so the detector finds the shape afterwards. But this is a speed bump against a determined actor, and it is the single largest gap between what the model claims and what it enforces.
- TWO OF THE SEVEN SHIPPED BLOCKERS ARE OUTSIDE ANY SCHEMA'S REACH. The dead-locals lint failure is code hygiene; the fourth inline `YR-` marker matcher in `board_plumbing.py:145` is a Python file the schema never sees. The model removes the PRESSURE for both (a loop over compiled rows has no per-act branches to rot; the funnel needs no matcher once `gh project item-edit` is a covered write path), and a tree-wide agreement test plus the deletion named in the migration removes the possibility. Until both land, discouraged, not impossible — and I will not claim schema authority over code the schema never sees.
- MULTI-STORE ATOMICITY IS NOT EXPRESSIBLE. `task.blocked->ready.unblock` writes both `board.status` and `board.reason`, but `gh project item-edit` writes one field per invocation and each invocation is a separate act. The engine classifies the intermediate cell — (Ready, Blocked) or (In Progress, none) — and, finding no lawful transition from it, refuses. It fails CLOSED, but the transition may be executable only through a single funnel act that performs both writes. The Adversary's design has the same hole and does not name it; this one names it and its resolution is a real implementation constraint on `board_plumbing.set_field`.
- SATISFIABILITY DEPENDS ON A REGISTRY AMENDMENT THIS DESIGN REQUIRES. Loader rule S needs a typed `emitted_by` column on every `records.toml` row; today's `emitter` is free prose ('the attended operator session (a comment on the epic's trail, record-before-flip)') and cannot be resolved to an actor class. Until that column lands, S cannot run and a transition walled by a record no declared actor can produce would still load.
- NO CROSS-MACHINE GUARDS. A transition may only guard on its own machine's facets and on named stores. 'Promote this slice only if its governing design is active' must be an `[[evaluator]]` with a real implementation, not a state predicate. The epic gate's sweep questions ('promote when three siblings are Done') are multi-instance and stay hand-written Python that reads this model for vocabulary only — the model deliberately grows no query language.
- NO TEMPORAL OR COUNTING CONDITIONS. `window = "since-store-change"` works only where a store declares a readable change clock — board items do, vault frontmatter does not. Elsewhere a presence guard is satisfiable forever by one old record. The loader refuses to let an author PRETEND otherwise (it rejects `window` on a clockless store), but the gap is real and unclosed. No `after_days`, no `at_least_n`; `shadow_complete` is a counting condition and lives inside the evaluator.
- GENUINENESS IS UNREACHABLE. Guards check existence and grammar only. `record_present("YR-DESIGN-FIT")` cannot tell a real fit check from `fit: yes`. That stays with independent review and the adherence bench, and the model says so in the compiled slice's footer rather than implying otherwise by silence.
- NO CONCURRENCY MODEL. Two attended sessions in one workspace share the journal and can produce a confused close report. Detection is idempotent; the report is not. The `process.toml` model itself is read-only at runtime, so there is no write race — only a reporting one.
- A LANE MANDATE OVER-DEMANDS BY CONSTRUCTION, AND ITS SCOPE IS COARSE. The union over a lane's on-course transitions is what a fully-travelled trail carries, not what a partially-travelled one does; `check_trail --transition <id>` is the sharper unit and exists for that reason. Separately, the compiled `epic` lane mixes records living on the EPIC's trail (YR-EPIC-APPROVAL) with records on a CHILD's (YR-AUTO-PROMOTED); the detector takes repeatable `--issue`, so both can be in scope, but the model does not express which trail each record belongs to. That is a real gap and the obvious next amendment.
- ENFORCEMENT AND STANCE BEING DERIVED COSTS DIFF LOCALITY. A reviewer reading `process.toml` alone cannot see that a change flipped a transition from `prevented` to `partial` — they must read `build/walled-acts.md` in the same PR. The artifacts are committed and `surfaces --diff` exists precisely for this, but it is a genuine trade against THE MINIMALIST's argument that a human should see the word change in the model file itself.
- THE MODEL MAKES RULES EXPRESSIBLE, EVALUABLE, AND DIFFABLE. IT DOES NOT MAKE THEM RIGHT. A wrong `actor` list, a `door` classified as reversible when its consequences are one-way, or a guard citing the wrong record will pass every check in this document. Row count is the canary: past roughly forty transitions the diff stops being reviewable in one sitting, and the right response is a debt round consolidating machines, not a bigger file.

## Open questions

### Is `process.py validate` advisory-tier (like `records.py` and `check_trail.py` today), or does it join `check_cmd` / CI as a gating check?

Why the owner: This is the ordering question the factory's own architecture turns on, and it cuts both ways. Gating means the enforcement layer's validator can break the build pipeline — the lane would acquire the power to stop the machine that builds it, inverting the dependency the factory depends on. Advisory means every honesty mechanism in this design (the derived enforcement values, the drift check that keeps `attended-lane.md` in sync, the amendment duty) is unenforced at exactly the moment a diff merges. Neither is a designer's call: it is a judgement about how much authority the attended lane may hold over the autonomous one, which is a standing ruling of yours (the pipeline builds under fixed gates).

- Fully advisory — validate runs in the epic-gate sweep and at session close only; a broken model degrades the walls but never blocks a build.
- Split tier — the LOAD-TIME rules (schema shape, closed vocabularies, rules P/F1/F2/D/A/C/R/S) gate in CI because a model that does not load means the walls are silently off; the DRIFT and AMENDMENT checks stay advisory because they are about review discipline, not correctness.
- Fully gating — validate plus drift plus amendment all in `check_cmd`, so a stale compiled surface fails the build.

**Recommendation:** The split tier. A model that does not load is not a style finding — it means the enforcement layer is off with nobody informed, which is the exact failure class this round exists to remove, and it is cheap and deterministic to check. Drift and amendment are review-discipline concerns and belong where review discipline lives (the sweep and the PR), not in a gate that can wedge a build over a regenerated markdown table. This keeps the lane unable to break the pipeline for anything but 'the walls are structurally broken'.

### Must `prevented` require a SERVER-SIDE chokepoint, or may full client-side write-path coverage earn it?

Why the owner: This decides what the word `prevented` PROMISES to every reader of every compiled surface — the map, the delivered slice, the close report. It is a truth-in-labelling policy, not a technical fact, and it will change what an agent believes it can and cannot do in every session from now on. THE ADVERSARY argued the strict rule (only GitHub branch protection and the like ever earn `prevented`); this synthesis's derivation currently allows full live client-side coverage to earn it. The strict rule is more honest and demotes almost everything to `partial`, which risks the slice's honesty block becoming uniform noise that agents stop reading.

- Strict — `prevented` requires a fresh server-side chokepoint. Essentially every hook-side wall reads `partial`, and the map's stance column carries little information.
- Coverage-based (as designed) — `prevented` when every write path of every store the transition writes is covered by a live binding, with unobservable paths counting as open. A handful of transitions earn it; the rest read `partial` with named holes.
- Coverage-based plus a separate `chokepoint` column, so a reader sees BOTH 'every known door is bound' and 'a server enforces it', and the two claims never collapse into one word.

**Recommendation:** The third. The strict rule is right that client-side coverage is a weaker promise, but collapsing both facts into one word throws away the distinction rather than expressing it — and a column where every row reads `partial` teaches nothing. Two derived columns cost nothing to compile, keep both claims honest, and let a reader see at a glance which walls survive a determined bypass and which merely survive an ordinary one.

### Should the compiled lane mandates be allowed to exceed today's hand-listed set — specifically, adding `YR-PROMOTED` to `standalone` and `YR-AUTO-PROMOTED` to `epic`?

Why the owner: Compiling the mandates from the transitions is a strict improvement in correctness (those records land 'by construction' at the funnel, so a trail without one means the flip happened outside it) — but it means every historical standalone and epic trail predating the funnel now produces a detector finding. That is a decision about how much noise the census and the close report may carry against attended attention, which is the same pricing judgement the round record already reserves for you.

- Compile freely — the detector reports findings on historical trails; treat the backlog of findings as a real (if low-priority) census signal.
- Compile freely but date-bound the detector — findings suppressed for scopes whose first record predates the model's `[model].version` 1.0.0 date.
- Pin the compiled lanes to today's hand-listed set for v1 via an explicit `mandate = false` marker on the two new records, and widen in a later amendment once the backlog is clear.

**Recommendation:** The second. The added records are genuinely right and I would not weaken the model to preserve a wrong hand-list, but a wall of findings about trails nobody will retro-fix is exactly the noise that trains people to ignore a detector. A date bound is one line in `check_trail`, keeps the model honest, and puts the findings where they are actionable — on trails built after the rule existed.

