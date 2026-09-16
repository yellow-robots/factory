## Looked at
- `list .` (root of the world)
- `read README.md`
- `read observer.py`
- `read test_observer.py`
- `read .gitignore`

## Found
- `observer.py` line 24-26: the world is the directory containing the script (`WORLD`), the run record directory is `runs/` under it, and the API key file is `~/.config/factory/deepseek.key`.
- `observer.py` lines 63-98 define exactly two functions the model may call, `list` and `read`; there is no write, edit, or delete function.
- `observer.py` lines 111-118: `_resolve` resolves a requested path against the world root and raises `outside the world` or `not part of the world` for anything outside the root or under a hidden top-level name; `runs` is the default hidden tuple (line 104).
- `observer.py` lines 28-32 fix the constants: endpoint `https://api.deepseek.com/chat/completions`, model `deepseek-flash`, `CALL_CAP = 40`, `LIST_CAP = 500`, `READ_LINES_CAP = 300`, `READ_BYTES_CAP = 32_000`.
- `observer.py` lines 120-135: `list` sorts entries directories-first by name, reports kind (link/dir/file), byte size for files, appends a "... N more entries not shown" line past `LIST_CAP`, and returns "(empty)" for an empty directory.
- `observer.py` lines 137-157: `read` returns numbered lines, disables further output at `READ_LINES_CAP` lines or `READ_BYTES_CAP` bytes and appends "... truncated; continue with start=<n>"; a non-file path is an error.
- `observer.py` lines 159-165: `call` returns the string `error: ...` for an unknown function name, a `TypeError`/`ValueError`/`OSError`, instead of raising.
- `observer.py` lines 36-61: the system role fixes the four headings `## Looked at`, `## Found`, `## Missing`, `## Unsure`, requires facts only with each Found claim naming its path, and instructs the model to stop when another read would not change the report.
- `observer.py` lines 191-230: the loop sends role + goal, executes every `tool_calls` entry, appends the result as a `tool` message, and ends when an assistant message has no tool calls, returning its content.
- `observer.py` lines 223-230: once `calls` reaches `CALL_CAP`, a user message says the cap is reached and to write the report, and subsequent provider calls are made with tools disabled (`tools=stopped == "answer"`, line 199).
- `observer.py` lines 168-188: each provider call sends `temperature: 0`, a 180-second timeout, and retries up to 4 attempts with `2 * 2**attempt` sleeps only on HTTP 429/500/502/503/504; any other HTTP error raises `RuntimeError`.
- `observer.py` lines 237-260: `main` exits 2 unless there is exactly one non-blank argument, reads the key from `KEY_FILE`, creates `runs/<UTC stamp>/`, and writes `goal.txt`.
- `observer.py` lines 249-251, 221: every message and every call is appended to `transcript.jsonl` as one JSON object per line with a timestamp, flushed after each write.
- `observer.py` lines 261-286: on success it writes `response.md` (the model's text unchanged), computes `numbers.json` (model, role hash, wrapper hash, turns, calls, token counts, lists, reads, files_read, lines_read, cost_usd, seconds), prints the run directory and the numbers, and returns 0; on `RuntimeError` it records an error entry, prints the error, and returns 1.
- `observer.py` line 34 and lines 272-280: cost is computed from fixed `PRICE` rates (cache_hit 0.006, cache_miss 0.3, output 1.2 USD per 1M tokens).
- `README.md` lines 5-8: usage is `python3 observer.py "<goal>"`, and the tests run with `python3 -m unittest -v` "without a provider".
- `README.md` lines 12-19 and `test_observer.py` line 58: the run record is `runs/<utc-stamp>/` with `goal.txt`, `transcript.jsonl`, `response.md`, `numbers.json`.
- `test_observer.py` lines 28-53: tests assert that `list .` shows `file\t14\ta.txt`, `dir\t0\tsub`, `link\t0\tescape` and omits `runs`; that `read` of `..`, `../..`, `/etc`, `escape`, `runs/secret` each returns a string starting `error:` and that `list ..` does; that a 1000-line file truncates at `READ_LINES_CAP + 1`; that `call("write", ...)` and `call("read", {"nope": 1})` return errors rather than crashing.
- `test_observer.py` lines 57-108: the loop test expects `record` roles in order `["system", "user", "assistant", "call", "call", "assistant"]`, accumulated token sums, and one `tool` message per tool call id.
- `test_observer.py` lines 110-143: the cap test expects `stopped == "cap"`, `calls == CALL_CAP`, and the final provider call to have `tools` False.
- `.gitignore` lines 1-2 ignore `runs/` and `__pycache__/`.

## Missing
- Nothing in the world documents a capability beyond listing and reading: `observer.py` lines 63-98 and 159-165 contain no function that writes, renames, or deletes anything in the world, and `test_observer.py` line 52 asserts `write` is an error.
- No fallback or default API key is present: `observer.py` line 243 reads `KEY_FILE` with no existence check or alternative shown.
- No behavior for zero or multiple command-line arguments other than the usage message and exit code 2 (`observer.py` lines 238-241).
- The world contains no record of a run: the listing of `.` (with `runs` hidden at the root, `observer.py` line 127) shows no `runs/` directory, so no `goal.txt`, `transcript.jsonl`, `response.md`, or `numbers.json` is available to read.
- Nothing in the world states what the DeepSeek `deepseek-flash` model will or will not return, or what the API accepts; the endpoint, model name, and pricing are only constants and comments in `observer.py` (lines 27-34).
- No code checks that the model's answer actually contains the four headings or follows the role rules; `observer.py` lines 261-262 write the text to `response.md` as received.
- `LICENSE` and `.git` (listed as `file 60` in the root listing) were not read, so their contents are not established here.

## Unsure
- Whether the program functions against the live provider cannot be determined from the world: the provider is a remote endpoint (`observer.py` line 27) and the tests substitute a scripted provider (`test_observer.py` lines 56-108, 110-143).
- What happens when `KEY_FILE` is absent, unreadable, or malformed: `observer.py` line 243 does the read before the `try` block at line 255, so the resulting error path is not shown in the source.
- Whether a run's directory name can collide (the stamp is second-resolution UTC, `observer.py` line 244) and whether `mkdir(parents=True)` without `exist_ok` fails on collision — the code at line 245 does not say.
- What the actual size/content of `LICENSE` and `.git` is, since neither was read.
- Whether the model in practice stops before `CALL_CAP` or how many tokens/cost a real run incurs; only accumulated counters and fixed price constants are present (`observer.py` lines 196-204, 262-282).
