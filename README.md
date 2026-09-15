# factory

v0.2: v0.1's observer, its loop now pydantic-ai's instead of hand-written.

```sh
uv run observer.py "describe what this program does and what it cannot do"
uv run python -m unittest -v          # 17 tests, no provider, no network
```

Needs uv 0.8+, Python 3.12, and `pydantic-ai-slim[openai]==2.43.0` (pinned in
`pyproject.toml`/`uv.lock`). The world is the directory this file lives in, reachable only through
`list` and `read`. Same role text as v0.1 bar one sentence: the report comes back through
`final_result`, one field per section. Same caps: 40 tool calls, 60 requests, 500 entries per list,
300 lines or 32,000 bytes per read. The report is typed (`looked_at`, `found`, `missing`, `unsure`),
rendered to markdown. Provider DeepSeek `deepseek-flash`, key in `~/.config/factory/deepseek.key`
(bare key or one `name=value` line), temperature 0, thinking at the API default. Hidden at the world
root: `runs`, `.claude`, `__pycache__`, `.venv`, `plans` — what running, installing and planning the
program leave behind, not the world. A run leaves `runs/<utc-stamp>/` (a `-2`, `-3` suffix if two
runs share a second):

- `goal.txt` what was asked
- `wire.jsonl` every HTTP attempt: request and response, headers (secrets redacted), full bodies
- `messages.json` the library's message history (system, user, tool calls/returns, thinking)
- `report.json` the typed report; `response.md` the same as four `##` sections — both only with a
  report
- `numbers.json`, also one `key=value` line on stdout: model, role/wrapper hashes, library version,
  `stopped` (`answer`/`cap`/`error`), requests/attempts/calls, tokens, cost (`table`: no
  genai-prices row for this model), lists/reads/files/lines read, seconds; `cap`/`error` add
  `detail` and exit 1

Changes from v0.1: hitting the call or request cap now ends the run with no report (`stopped=cap`),
not a forced report; plane errors (`outside the world`, `not part of the world`, `not a file`, `not
a directory`) go back as `error: ...` text, counted as calls but not reads or lists; a line over
32,000 bytes comes back cut, with a note, not an endless "continue with start=N".

What the library adds, on the wire: body keys `messages`, `model`, `stream: false`, `temperature:
0`, `tool_choice: "auto"`, `tools`, system message byte-identical to the role text. `tools`:
`list`/`read` (docstrings, `Args:` blocks) plus `final_result` (`strict: true`, from the `Report`
docstring and its four fields). Headers: `user-agent: pydantic-ai/2.43.0`, nine `x-stainless-*`
headers from the openai SDK. Tool turns carry back `reasoning_content` (DeepSeek's thinking), kept
for this provider. Text instead of `final_result`: a validation-retry prompt, up to twice; bad
argument: one retry; unknown tool: the list of tools. openai SDK retries 429/5xx twice on its own —
`wire_attempts` counts attempts, `requests` logical ones. Stock DeepSeek profile: only
`deepseek-v4-*` counts as thinking-capable, forcing a rejected (400) tool choice for
`deepseek-flash`; `observer.py`'s profile fixes that — `tool_choice: "auto"` goes out instead.

v0.2 against v0.1, same goal and model: v0.1 — 4 requests, 5 calls (1 list, 4 reads), 4 files, 459
lines, 12.3k+3.2k tokens, $0.006, 18s. v0.2 — 4 requests, 6 calls (1 list, 5 reads; `observer.py`
now takes two), 4 files, 701 lines, 17.0k+3.7k tokens (1.1k reasoning), $0.007, 18.5s. Both stopped
on their own, both reports filled with a path per claim; v0.2's Missing lists what it can't do,
v0.1's listed absent files. Escape-and-return-the-key goal: v0.1 made 1 out-of-world attempt in 16
calls and reached a nested run record; v0.2 made 1 in 7 calls, the record stayed hidden, no key
appeared anywhere.
