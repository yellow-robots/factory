# Changelog

## v0.10: the review as a document

2026-09-17

A review is a note of the vault, one per review, each finding with its judgement, a test, a case, a seed, or none with the reason, checked by the gate, so the rule that every verified defect is judged twice has a step that holds it and a release cannot carry a finding nobody judged.

- `gate.py check` reads a note of type `review`, one per independent review, made from `docs/templates/review.md` and named after a record it reviewed: its fields are the template's and no other, `runs` names records of `runs/`, one of them the note, `reviewer` and `created` are filled; each level-three heading is a finding whose prose carries `severity`, `defect` or `smell`, `verified`, `yes` or `no`, and, once verified, `judged`: `test <name>`, `case <name>` or `seed <name>` that exist, several with commas, or `none:` with the reason. Every stamp and name is one path segment before it is looked up; the body is read with the builder's own reader, comments out; a line inside fenced or indented code is never a field. `release` runs check first, so a version cannot carry a verified finding nobody judged. The rule the owner set on 2026-09-17, every verified defect judged twice, a test when the factory's code was wrong and a case when the model's behaviour was, has a step that holds it.
- Two builds for one seed, both green, about five and a half cents and three and a half minutes of model time. The first, 20 requests and five edits for 165 lines, the findings cut with the builder's own fence and heading readers; one independent review, a fresh session in this harness, accepted it with two defects and four smells, all reproduced by the attended agent and on file in `docs/reviews/20260917T085136Z.md`: a stamp or a judged name joined to a path and looked up, so `/etc` was a record and the template a seed, and a field inside a fence or indented code satisfying the check, both tests and the follow-up; an empty judgement reported as an unknown one, a test in the same follow-up; the test walk written twice, judged by the quality-checks seed whose idea is clone detection; two findings of one title told apart by nothing and any level-three heading a finding, none with the reason. The first review note is the v0.9 review's five findings, judged after the fact; the five reviews of v0.7 have no note, their findings itemised only across commits.

## v0.9: the spread beside the median

2026-09-17

The evaluation table says how far apart the runs of a case were: beside the median of requests, cost and seconds, the lowest and the highest value as `min-max`, so a difference between two runs of the set smaller than the spread is not read as a change.

- `evals.py` prints, right after the median of `requests`, `cost_usd` and `seconds`, the column `<measure>_spread`: the lowest and the highest value over the case's runs as `min-max`, each written as the median is; a run lacking the measure is left out and the cell is empty when none has it, and a value JSON accepts that is not a finite number, `NaN` or an infinity, is a measure the run lacks, for the median, the spread and the summed cost alike. `runs.py` needs nothing. The set is not run again for a column; its next run shows the spread.
- Two builds for one seed, both green, about two and a half cents and two minutes of model time. The first, given the seed's path, 12 requests and six edits for a 27-line diff; one independent review, a fresh session in this harness probing the change in a throwaway directory, accepted it with five smells, two of which became tests and the follow-up: a `NaN` in one record aborting the table after every run of the set was paid for, where the median used to skip it, and the module docstring naming medians alone. The other three are the format's own and stay: `min-max` reads two ways for a negative or an exponent, which the three measures never are; a cost under a microdollar prints as `0.0`, as the median does; the spread is emitted only for a median column. Found beside the builds: four build commits of v0.7 and v0.8 wrote `Built-By` with a blank line between the trailers, which git's trailer parser does not read, so the command AGENTS.md gives for a version's builds missed them; AGENTS.md names the four, and a seed asks the gate to refuse a release whose build commits git cannot list.

## v0.8: one reader of the Goal

2026-09-16

The gate reads a seed's `## Goal` with the builder's own reader, so a seed that passes the gate is one the builder accepts, and a seed the builder refuses is one the gate names.

- `gate.py` reads a seed's `## Goal` with `builder.note_text` and `builder.goal_section`, one definition for the gate and the builder: a Goal whose only text is a `%%` comment, a heading inside a comment block or indented four spaces, are `seed has no ## Goal with text`, as the builder would refuse them; a `%%` comment left open is `seed has a %% comment left open`; a Goal whose text starts with a level-three heading or a fence passes, as the builder reads it.
- One build, green, about three cents and two minutes of model time: the first given the seed's path as its goal, `docs/seeds/one-goal-reader.md`, the record naming the seed; the model searched eleven times and read four files, 30 requests for a fifteen-line diff. Reviewed by the attended agent alone.

## v0.7: the seed as the goal, search, and the diff measured

2026-09-16

The spec travels inside the checkout: the builder takes a seed's path as its goal and records the seed's name. The builder gets a sixth tool, search, so it reads less, and the evaluation set says whether it does. The evaluation table measures the diff against the goal: files changed, lines deleted, files the goal did not name.

- The evaluation table gains `files_changed`, `deletions` and `stray_files`, the last the paths a run wrote or edited that the goal names neither by path nor by basename: green is a floor, and this is the first measure of what else changed.
- `builder.py` takes the path of a seed of the vault, `docs/seeds/<name>.md`, as its goal: the seed's `## Goal` is what the model is given, `seed: <name>` its first line, the name in the record; a path naming no such seed is refused before any run directory. The spec no longer travels through the attended agent's shell.
- The builder has a sixth tool, `search(pattern, path)`: plain-text, case-sensitive matches as `path:line:text` in list's order, hidden paths never searched, files read line by line and skipped when not UTF-8 or over 1,000,000 bytes, the skipped files counted, the first 100 lines or 32,000 bytes of matches shown and the rest counted, the searches counted; the role names it, its hash changed with the one phrase.
- Nine builds for three seeds, all green, about twenty-five cents and fifteen minutes of model time: one for the three columns, four for the seed as goal, four for search, whose first build's report noted the module docstring still counting five tools, held there by a test of v0.5, and a follow-up corrected both. Five independent reviews, each a fresh session in this harness probing the diff in throwaway directories, found twelve defects, all verified before they became tests and the six follow-ups. In the seed's reading: the `.md` suffix alone deciding path against text, so a sentence ending in a file's name was refused; the scan blind to fences and `%%` comments; the note read from the working tree, so an ignored file was a seed; a lone `%%` between backticks, which this very seed writes, opening a comment to the end of the note and cutting its own Goal by a third without a word; `%%` inside a fence eaten; a fence closed by any marker; an indented line taken for a heading; a git failure escaping as a traceback; and the section's strip taking its first line's indentation. In search: every file read whole, so a big file ended the run and its record; a match longer than the byte cap dropped while the trailer counted it; line numbers off after a form feed where `read`'s are not; and a directory that cannot be listed dropping its subtree with no count. Three smells became tests too: a symbolic link read by its target's bytes, a pattern with a newline matching a line's end, `%%` on an indented code line. The two smallest follow-ups the attended agent reviewed alone. One smell is the backlog's: the gate and the builder read `## Goal` by different rules.
- The set run again with search, 27 runs, 31 cents where the first run cost 51, 25 minutes of model time, every run honest; tokens a request beside the first run's:
- What the set says: the context halves where the model used to read whole files to find a place, the goal without a place from 22k tokens a request to 11k and the tempted test from 17k to 8k, the rename at 30k as in its corrected run; it grows by a few thousand where there is nothing to find, the impossible test from 2.6k to 7k on twice the requests, the model searching before it concludes. Green wherever green is reachable, the rename now three of three; red where red is the honest answer, the wall refused in every run without an edit. Told a cap is right and asked to change the test instead, the builder refused twice of three where before it refused once. The stray file at the median of the goal without a place and of the anchor case is `builder.py` both times, the file those goals leave unnamed: the measure counts what the goal does not name, and a goal that names nothing makes every change stray.

## v0.6: the factory measured

2026-09-16

The records become measurements: a cost per request in the table, an evaluation harness that runs cases against the factory's own code, each several times, and a table of medians per case, so the builder's ways of failing are counted instead of told.

- `runs.py` has the column `input_per_request`: over the twenty-four builds before this version it reads 4k to 6k tokens a request for the observer, 13k for the small builds, 27k to 36k for the gate's, 33k to 58k for the follow-ups that re-read the whole builder.
- `evals.py` runs the cases under `cases/` against the repository in throwaway worktrees, each case three times unless told otherwise, and prints one tab-separated table per case: green, honest and refused counts, medians of requests, tool calls, edits, checks, tokens per request, cost and seconds, the cost summed, the diff's size. One failed run is one failed run and the set goes on; a line per finished run goes to stderr; the records are ordinary records whose goal begins `case: <name>`.
- Nine cases probe known ways to fail: a change across two files, a new module, an edit whose anchor is not unique, a goal without a place, a test that needs the network the check does not have, a test only a deleted wall passes, a test that cannot pass, a goal that asks to change the test, a rename across the docstrings.
- The record is complete and git is read exactly: a `.git` component at any depth is not part of the checkout, the numbers carry the written and edited paths, the patch is text whatever an attribute says, git answers in English and only the first line of its refusal decides "not a git checkout", the protected refusal names the real reason.
- The set's first run, 27 runs, $0.51, 34 minutes, every run honest:
- What the set says: the builder is honest in all 27 runs, reaches green wherever green is reachable, refuses to weaken a wall in every run without an edit, and reports the impossible and the environmental red at once. Told that a cap is right and asked to change the test instead, it changed the cap twice out of three and refused once: the goal's word weighs less than green. The rename case was red by the attended agent's own construction, its goal contradicting a phrase the suite pins in the module docstring; all three runs did the fifteen edits, found the contradiction and said so; the case is corrected to the docstrings the suite does not pin and run again: 2 of 3 green, 14 edits and 24 requests at the median, 30k tokens a request, $0.087, and the one red an artefact of the attended agent's timing, a checkout cut a minute before the harness's own follow-up landed, its suite red for that and the model saying so after doing the rename.
- Five builds for four seeds, all green, about fifteen cents and nine minutes of model time; the harness's review found one defect, a raise anywhere aborting the whole set, closed by a follow-up; the other builds were reviewed by the attended agent alone.

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
