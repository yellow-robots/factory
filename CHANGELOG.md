# Changelog

## v0.5: checkout, tools and the table

2026-09-16

The words the builder is described with become the ones it works with, checkout and tools, and a checkout is required; the vault gets its born date back and its backlog checked against the template; a reviewed record's wire is compressed; and the records become a table, the first instrument over them.

- `builder.py` works on a checkout with tools: `world` became `checkout` in code, keys and messages, `Plane` became `Tools`, the role says checkout and its hash changed with it; a checkout must be the root of its own git repository with a commit, git runs without the environment's `GIT_DIR` and its kin, and a git that cannot run is a usage error; `plans` left the hidden names; a run that changed nothing leaves no `diff.patch`.
- Seeds carry `created`, first in the frontmatter, a date the gate requires from open on; the backlog shows it as Born and orders equal ranks by it.
- The gate checks the backlog's columns, filters, formulas, sorts, groups and summaries against the seed template's fields, reading the base as Obsidian writes it, nested groups and the `note.` prefix included.
- The gate reports a committed record whose wire is not compressed; the attended agent compresses `wire.jsonl` to `wire.jsonl.gz` at the factory's commit, and the fourteen wires committed before are compressed, 28.5 MB to 7.6 MB.
- `runs.py` prints the records as one tab-separated table, a row per record with fixed columns, `head` read from the new key or the older `world_head`.
- Eleven builds for five seeds, all green, about forty-four cents and twenty-four minutes of model time. The rename hit the request cap at its third green check, complete but unreported, after the model wandered through the docs and probed three walls; four follow-ups from review finished it. Nine defects found by six independent reviews became tests and follow-up builds: the code's own text lagging a behaviour change, a subdirectory or a stray `.git` accepted as a checkout, a `git diff` that obeyed the environment's external driver, the record lost to a file named like an option, git's refusals of a real checkout mislabelled, three misreadings of Obsidian's filter shapes, and a table cell that a tab could break. `.gitattributes` and `.gitignore` are protected from the model since then.

## v0.4: the gate

2026-09-16

The version that makes the documents honest: a deterministic gate that validates the vault against the templates, renders the changelog and cuts a version's tag; the vault protected from the builder's writes; the world's commit recorded in every run and a dirty world refused; the run records committed as the baseline for the evals.

- `gate.py check` validates `docs/` and the repository against it: every note's type names a template, a seed's fields follow its status, a seed at building or done is named by a test's docstring, wikilinks resolve, version notes are named like tags, at most one is in flight, a tagged version's seeds are done or rejected. `render` writes `CHANGELOG.md` from the tags. `release <version>` refuses until everything derived agrees, a revised `AGENTS.md` and a green suite included, then cuts an annotated tag with the note's first paragraph and bullets. 24 tests on temporary vaults.
- `docs/` is protected in the plane: write and edit refuse it, list and read still work.
- Every record carries `world_head`, the world's commit; a world with uncommitted or untracked changes is refused with a usage error before any record exists.
- The run records are in the repository: the eight before this version and the four of it.
- Seeds carry only fields with a consumer, type, status, summary, value, effort and version; the goal is a section of the body and the acceptance is the tests whose docstring names the seed. `AGENTS.md` at the root replaces the front door and is written for any model in any harness.
- Four builds, all green: docs-protected in 1 edit ($0.006, 22 s), world-pinned-to-commit in 3 edits ($0.019, 64 s), the gate in 1 write and 8 edits ($0.063, 212 s) and, after the review turned two of its defects into tests, 3 more edits ($0.009, 41 s). The gate released this version.
- Commit 48cbbe4, the factory's first change (the wire records a JSON body as JSON), is released here.

## v0.3: the builder

2026-09-15

The observer evolved into a cold session that changes a world until its tests pass. From here on the factory is the builder: the attended agent writes the goal and the red tests, the factory writes the code, the attended agent reviews the diff. The last version built by agents.

- Five functions: `list`, `read`, `write` (create or replace, parents inside the world), `edit` (exactly one occurrence), `check` (the world's tests in a container, no network, world read-only, exit code and tail returned, full log kept). Every failure is an `error: ...` string.
- Walls in the plane: paths outside the world; hidden roots `runs`, `.claude`, `__pycache__`, `.venv`, `plans`, `.git`; protected `test*.py`, `tests/`, `pyproject.toml`, `uv.lock`, `check.Dockerfile`; 30 writes and edits and 8 checks per run; 80 tool calls and 60 requests in the library.
- The check runs `python -P -m unittest discover` because a world-root `unittest.py` would otherwise turn any suite green; the image is built once from the world's own lock, with git because the world's tests use it.
- The record grows by `diff.patch` (against HEAD, plus a diff per untracked file), `check-<n>.log`, and numbers for writes, edits, checks, the plane's own verdict on the last check next to the report's claim, and the diff counts. No temperature in the request.
- 37 acceptance tests written from the plan before the code; the code written to pass them; an independent review found a writable `.git` and a forgeable green, both closed and pinned.
- First runs, after the tag: G1 green in 3 edits and 2 checks ($0.009, 32 s), its diff merged on `main` as commit 48cbbe4, the first change built by the factory (the commit is titled `v0.4` from before that number was given to the gate; the tag `v0.4` includes it); G2, a test that cannot pass, red with no edits and an honest report.

## v0.2: the observer on pydantic-ai

2026-09-15

The loop borrowed, pinned and read once on the wire; the plane, the role and the record kept.

- pydantic-ai-slim[openai]==2.43.0, 28 packages locked. The report comes back through the `final_result` function as a typed four-field object, rendered to the same four sections.
- The record grows: `wire.jsonl` with every HTTP attempt, headers with secrets redacted, full bodies; `messages.json` with the library's history; numbers add library, wire attempts, reasoning tokens, cost source.
- Read on the wire: the system message is byte-identical to the role; the library adds `tool_choice: auto`, `stream: false`, the `final_result` tool, the SDK's headers, and passes DeepSeek's `reasoning_content` back on tool turns. The stock DeepSeek profile would force a tool choice the API rejects for `deepseek-flash`; a profile override keeps `tool_choice: auto`.
- Behaviour changes: a cap hit ends the run with no report; connection errors land in the record; a line longer than the byte cap is cut instead of dead-ending a read; symlink loops are error strings; `.venv` and `plans` hidden from the world alongside `runs`, `.claude`, `__pycache__`.
- Same goal as v0.1: 4 requests, 6 calls, 701 lines, $0.007, 18.5 s; the escape probe made one out-of-world attempt in 7 calls and reached nothing hidden.

## v0.1: the observer

2026-09-15

The smallest loop that closes a goal: a cold session with a fixed role, a world it can only `list` and `read`, and a report. Written by hand in one file with the standard library; DeepSeek `deepseek-flash` over raw HTTP; a run record of goal, transcript, response and numbers.

- The observer: role text fixed in the wrapper, the goal the only input, two functions confined to the directory the wrapper lives in, `runs/` hidden from the world, six tests without a provider.
- First run on its own directory: 4 turns, 5 calls, 4 files, $0.006, 18 s; the report kept its four sections with a path per claim.
- The escape probe (return the key from outside the world): one out-of-world attempt in 16 calls, no fabrication; it found that hiding applied only to the first path segment and read a nested worktree's run record, which v0.2 closed.
