## Looked at
- .
- README.md
- observer.py
- plans
- pyproject.toml
- observer.py (from line 301)
- test_observer.py
- plans/v0.2.md

## Found
- observer.py:1-12 docstring says the program is the observer, 'a cold session that looks at a world and reports. Factory v0.2', run as `uv run observer.py "<goal>"`; the world is the directory the file lives in, reachable only through two functions, list and read.
- observer.py:41-45 sets WORLD = the directory containing observer.py, RUNS = WORLD/'runs', KEY_FILE = ~/.config/factory/deepseek.key, MODEL = 'deepseek-flash', LIBRARY = 'pydantic-ai-slim 2.43.0'.
- observer.py:46-53 sets TOOL_CALLS_CAP = 40, REQUEST_CAP = 60, LIST_CAP = 500, READ_LINES_CAP = 300, READ_BYTES_CAP = 32_000, HIDDEN = ('runs', '.claude', '__pycache__'), and a USD/1M-token PRICE table.
- observer.py:109-184 class Plane exposes exactly two operations: `list(path)` returns one entry per line as 'kind\tsize\tpath' sorted dirs-first, and `read(path, start)` returns file content as numbered lines; both catch ValueError/OSError and return an 'error: ...' string rather than raising.
- observer.py:119-126 `_resolve` resolves against the world root and raises ValueError 'outside the world' for paths whose resolved parent chain does not contain the root, and 'not part of the world' when the first path segment is in HIDDEN.
- observer.py:147-148 list appends '...\tN more entries not shown' past LIST_CAP; observer.py:174-175 read appends '...\ttruncated; continue with start=<i>' at the line/byte cap.
- observer.py:55-80 ROLE instructs: explore first then report; return the report through the `final_result` function with fields for '## Looked at', '## Found', '## Missing', '## Unsure'; facts only; each Found claim names its path; read only what the goal needs; stop when another read would not change the report.
- observer.py:83-92 class Report has exactly four fields, looked_at, found, missing, unsure, each a list[str]; observer.py:98-106 render writes four '## ' headings with '- ' bullets and '- (none)' for an empty field.
- observer.py:236-251 `build_agent` builds Agent(model, instructions=ROLE, output_type=Report, tools=[Tool(plane.list), Tool(plane.read)], model_settings=OpenAIChatModelSettings(temperature=0, timeout=180), retries={'tools': 1, 'output': 2}).
- observer.py:224-233 the model is OpenAIChatModel('deepseek-flash', provider=DeepSeekProvider(...), profile=PROFILE) where PROFILE sets supports_thinking=True, openai_reasoning_enabled_by_default=True, openai_supports_forced_tool_choice_with_thinking=False; the comment says this makes the library send tool_choice: auto so DeepSeek does not return 400 'Thinking mode does not support this tool_choice'.
- observer.py:254-270 `run` calls agent.run_sync(goal, usage_limits=UsageLimits(tool_calls_limit=40, request_limit=60)); UsageLimitExceeded yields stopped='cap', UnexpectedModelBehavior/ModelHTTPError yield stopped='error', and in both of those cases report is None.
- observer.py:187-221 class Wire logs every HTTP attempt to wire.jsonl as {t, dir: 'request'|'response', method, url, status, body}; the docstring at line 188 says the Authorization header and key are never written.
- observer.py:277-335 main requires exactly one non-blank CLI argument (else usage to stderr, exit 2), reads the key from KEY_FILE, makes runs/<utc-stamp>/, writes goal.txt, wire.jsonl, messages.json, report.json and response.md (only when a report exists) and numbers.json, prints the run dir and one numbers line, and returns 0 only when stopped=='answer', else 1.
- observer.py:307-327 numbers.json records model, role and wrapper sha256 hashes, library, stopped, requests, wire_attempts, tool_calls, token counts, cost_usd and cost_source ('genai-prices' or 'table'), lists, reads, files_read, lines_read and seconds.
- observer.py:52-53 and 299-306 comment that genai-prices has no deepseek-flash row, so `usage.cost` is None and the PRICE table is the fallback, with the source recorded.
- test_observer.py:1 docstring: 'The plane, the report and the loop, checked without a provider. uv run python -m unittest -v'; test_observer.py:26 sets models.ALLOW_MODEL_REQUESTS = False.
- test_observer.py:64-70 asserts reading or listing '..', '../..', '/etc', 'escape', 'runs/secret', '.claude/secret', '__pycache__/secret' returns an error, and that list('../..') says 'outside the world', list('.claude') says 'not part of the world', leaving read_paths and listed empty.
- test_observer.py:56-62 asserts list('.') shows file/dir/link kinds and hides every HIDDEN name; test_observer.py:83-86 asserts a directory read, a file list and a missing path return an 'error: ...' string instead of crashing.
- test_observer.py:143-154 asserts that a model which only ever calls `list` stops with stopped=='cap', report None, and exactly TOOL_CALLS_CAP=40 executed calls; test_observer.py:156-171 asserts a plain-text answer is answered with a library retry prompt containing 'Invalid JSON' and 'Fix the errors and try again'.
- test_observer.py:174-210 asserts main writes exactly goal.txt, messages.json, numbers.json, report.json, response.md, wire.jsonl; response.md starts with '## Looked at'; cost_source is 'table'; the API key string is absent from messages.json; and exit code is 0.
- pyproject.toml:1-7 declares project 'factory' version 0.1.0, requires-python >=3.12, dependencies = ['pydantic-ai-slim[openai]==2.43.0'].
- README.md:1-12 describes 'factory', 'v0.1: the observer', usage `python3 observer.py "<goal>"` and `python3 -m unittest -v`, the provider DeepSeek (deepseek-flash) with the key in ~/.config/factory/deepseek.key, and a run leaving runs/<utc-stamp>/ with goal.txt, transcript.jsonl, response.md, numbers.json.
- plans/v0.2.md:1-18 states v0.2 is the observer rebuilt on pydantic-ai with the same plane, near-identical role text, a typed four-field report and the same caps; plans/v0.2.md:218-221 lists 'Out of scope': roles other than the observer, a second world, evals across models, agent.iter, hooks/MCP/Logfire/graph/durable features, any deploy target or forge workflow.
- plans/v0.2.md:31-39 and 224-228 state the gotcha-1 fallback (thinking=False) and the profile fix for the DeepSeek forced-tool_choice 400, and plans/v0.2.md:72-75 record decision 2 that a cap hit is a failed run with no report and decision 3 that thinking is left at the API default with temperature 0.

## Missing
- No runs/ directory or run record is visible in '.' (list '.'), and observer.py:51 hides 'runs' at the root, so the world contains no transcript of an actual execution to confirm the described behaviour at runtime.
- README.md describes only v0.1 (transcript.jsonl, `python3 observer.py`), and there is no README section on v0.2's files (wire.jsonl, messages.json) or on the cap-changes the code implements.
- The world contains no list of what the program cannot do: limits and prohibitions exist only as constants, caps and tests inside observer.py and test_observer.py, not as prose documentation.

## Unsure
- Whether the PROFILE workaround makes the live DeepSeek API accept the forced/output tool choice cannot be determined from the world; observer.py:224-233 and plans/v0.2.md:31-39 describe it as a fix, but no run record is present to confirm it.
- The actual output text the model produces for a given goal, and hence whether the four report sections are filled as the ROLE asks, cannot be determined from the source, tests or plans alone.
- Only the code path checked by test_observer.py (a FunctionModel) is evidenced; live behaviour of pydantic-ai 2.43.0 and httpx2 at run time is not observable from the world.
- The content of the 55-byte '.git' file (shown as a file, not a directory, in list '.') was not read, so whether the world is a git worktree cannot be confirmed; it does not bear on what the program does.
