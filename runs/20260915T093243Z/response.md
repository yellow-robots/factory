## Looked at
1. `.` (list)
2. `README.md` (read)
3. `observer.py` (read)
4. `test_observer.py` (read)
5. `.gitignore` (read)

## Found
- `observer.py` is a Python 3 script invoked as `python3 observer.py "<goal>"`; `README.md` line 6 and `observer.py` line 4 both state this.
- `observer.py` lines 24–32 define the world as the directory containing the file (`WORLD = Path(__file__).resolve().parent`), a runs directory (`RUNS = WORLD / "runs"`), the key path `~/.config/factory/deepseek.key`, the endpoint `https://api.deepseek.com/chat/completions`, the model string `deepseek-flash`, and caps: `CALL_CAP = 40`, `LIST_CAP = 500`, `READ_LINES_CAP = 300`, `READ_BYTES_CAP = 32_000`.
- `observer.py` lines 36–61 define a fixed system role (`ROLE`) that instructs the model to produce a report with the four sections `## Looked at`, `## Found`, `## Missing`, `## Unsure`, facts only, each Found claim naming a path, and to stop when another read would not change the report.
- `observer.py` lines 63–98 expose exactly two functions to the model: `list` (one directory, one entry per line as kind, size, path, relative to world root) and `read` (numbered lines, from 1-based `start`, capped at 300 lines or 32,000 bytes per call).
- `observer.py` lines 101–165 (`class Plane`) implement the execution plane: `list` sorts entries directories-first, reports `link`/`dir`/`file` and file sizes, and appends a `... N more entries not shown` line past `LIST_CAP`; `read` prints `N<TAB>line`, appends `... truncated; continue with start=<next>` when capped, and counts lines read; `call` returns an `error:` string for unknown function names and for `TypeError`, `ValueError`, `OSError`.
- `observer.py` lines 104–118: `Plane.hidden` defaults to `("runs",)`; `_resolve` resolves symlinks and raises `ValueError` for paths outside the world root or whose first path segment is hidden, so `..` and `runs/...` are rejected.
- `observer.py` lines 120–126: at the world root, hidden names are filtered from listings; nested directories are not filtered by name, only the top-level segment check in `_resolve` applies.
- `observer.py` lines 168–188 (`complete`) sends `temperature: 0`, includes `tools` only when `tools=True`, uses a 180-second timeout, retries 4 attempts on HTTP 429/500/502/503/504 with sleeps `2 * 2**attempt`, and raises `RuntimeError("provider HTTP <code>: ...")` for other HTTP errors.
- `observer.py` lines 191–230 (`run`) is the loop: system role plus goal are recorded first; each turn calls the provider, accumulates `turns`, `prompt_tokens`, `completion_tokens`, `cache_hit_tokens`, records the assistant message, executes each `tool_call`, records each call as `{"role": "call", ...}`, appends `{"role": "tool", "tool_call_id": ...}` messages, and returns the assistant text when no tool calls are present (labeling `stopped = "answer"`).
- `observer.py` lines 223–230: when `calls` reaches `CALL_CAP`, `stopped` becomes `"cap"`, a user message "The call cap (40) is reached. Write the report now from what you have." is appended and recorded, and subsequent provider calls are made with `tools=False` (line 199).
- `observer.py` lines 237–260 (`main`): requires exactly one non-empty argument else prints usage and returns 2; reads the key file text and takes the substring after the last `=` with surrounding quotes stripped (line 243); creates `runs/<UTC %Y%m%dT%H%M%SZ>/`; writes `goal.txt` and opens append-mode `transcript.jsonl`; each `record` writes one JSON line with a `t` timestamp and flushes.
- `observer.py` lines 261–286: writes `response.md` (adding a final newline if absent) and `numbers.json` containing `model`, `role` and `wrapper` as 16-char SHA-256 prefixes, turn/token counts, `lists`, `reads`, `files_read`, `lines_read`, a computed `cost_usd`, and `seconds`; prints the run directory and a `key=value` summary.
- `observer.py` lines 33–34 and 262–280: `cost_usd` is computed from a hardcoded `PRICE` table described in the comment as "USD per 1M tokens, peak rates", with `cache_miss` derived as `prompt_tokens - cache_hit_tokens`.
- `observer.py` lines 255–260: on `RuntimeError` the error is recorded in the transcript, `error: ...` is printed to stderr, and the process returns 1.
- `README.md` lines 11–19 describe the same run artifacts: `goal.txt`, `transcript.jsonl`, `response.md`, `numbers.json` with turns, calls, files and lines read, tokens, cost, seconds, and hashes of the role and wrapper.
- `README.md` lines 2–3 describe this as "v0.1: the observer. A cold session that looks at a world and reports."
- `test_observer.py` line 2 and `README.md` line 7 state `python3 -m unittest -v` checks the execution plane and loop without a provider.
- `test_observer.py` lines 28–53 assert: the root listing hides `runs` and shows `file`/`dir`/`link` kinds; paths `..`, `../..`, `/etc`, a symlink pointing outside, and `runs/secret` are errors; `read` numbers lines, truncates with `continue with start=301`, honors `start=990`, and accumulates `lines_read`.
- `test_observer.py` lines 51–53 verify unknown function names and wrong argument names return `error:` strings rather than raising.
- `test_observer.py` lines 56–143 test the loop with a scripted provider: multiple tool calls in one turn are executed and recorded in order with matching `tool_call_id`s, the text answer ends the run, and the call cap forces a final provider call with `tools=False` and `stopped == "cap"`.
- `.gitignore` lines 1–3 ignore `runs/`, `__pycache__/`, and `.claude/worktrees/`.
- The world root listing of `.` shows `.claude` (dir), `.git` (dir), `__pycache__` (dir), `.gitignore` (38 bytes), `LICENSE` (1070 bytes), `README.md` (748 bytes), `observer.py` (11314 bytes), `test_observer.py` (6068 bytes); no `runs/` directory is present in the listing.

## Missing
- No mechanism in `observer.py` (lines 159–165, 63–98) to write, edit, delete, move, or execute anything in the world; only `list` and `read` exist, and any other function name returns an error string.
- No code that validates or enforces the report structure named in `ROLE` (`observer.py` lines 36–61); the four headings exist only as prompt text.
- No resume, checkpoint, or multi-goal support in `observer.py`; `main` accepts exactly one goal argument (lines 238–241) and `run` starts fresh messages each call (line 193).
- No handling of two runs starting within the same UTC second: the run directory name has one-second resolution (line 244) and `run_dir.mkdir(parents=True)` (line 245) has no `exist_ok`, so a collision is unaddressed in code.
- No test of the network path in `observer.py` lines 168–188 (`complete`): retry behavior, 180-second timeout, and HTTP error text are not exercised by `test_observer.py`, which injects a scripted provider (lines 94–97, 116–137).
- No provider or endpoint other than DeepSeek's `chat/completions` with model `deepseek-flash` (`observer.py` lines 27–28); the model name and endpoint are constants.
- No tokenizer or billing lookup: `cost_usd` relies on the fixed `PRICE` table and the comment's dated source (`observer.py` lines 33–34).
- No streaming: `complete` reads the full JSON response at once (`observer.py` lines 180–181).
- No response file when the provider fails: `response.md` is written only after `run` returns successfully (`observer.py` line 261), while the error path returns 1 before that (lines 257–260).
- The `numbers.json` field `stopped` (set in `run` at lines 210 and 141 via tests) is not present in the `n` initializer at `observer.py` line 196; it is only added on return.
- No presence or content of `runs/` in the world: `Plane` hides it (`observer.py` line 104) and it is absent from the root listing, so no prior run records are reachable by the reader.

## Unsure
- Whether `~/.config/factory/deepseek.key` exists or holds a usable key: the path is inside `observer.py` (line 26) but outside the world, and nothing in the world confirms it.
- Whether `deepseek-flash` and the endpoint are currently valid, and whether the `PRICE` values match current billing; the world only contains the constants and the comment citing a 2026-09-15 reading (`observer.py` line 33).
- Whether the provider actually returns the `usage` fields (`prompt_cache_hit_tokens` etc.) the code reads (`observer.py` lines 200–204); no response fixtures or sample transcripts are present in the world.
- How the program behaves on non-UTF-8 or binary files: `read` opens text mode with `errors="replace"` (`observer.py` line 144) and no test covers it (`test_observer.py`).
- What `LICENSE`, `.git`, `.claude`, and `__pycache__` contain; they appear in the root listing of `.` but were not read, and they do not bear on the described behavior.
- Whether `observer.py` runs correctly against the live API; `test_observer.py` substitutes a scripted provider and states it checks the plane and loop "without a provider" (line 1).
