---
created: 2026-09-16
type: seed
status: done
summary: The builder explores a checkout file by file; a larger checkout needs search and a map, once the cost curve says so.
value: 3
effort: M
version: v0.7
---

## Evidence

Owner's item 3, 2026-09-16. G1 read the whole of `builder.py` in three calls to change nine lines of it; the escape probes read everything they could reach. The `input_per_request` column of v0.6 says the curve: 4k to 6k tokens a request for the observer, 13k for a small build, 33k to 58k for the follow-ups that re-read the 700-line builder, 35k for the rename case; the reads are the cost.

## Goal

`Tools` gains a sixth tool, `search(pattern, path=".")`, registered after `read`: every line of every file under `path`, the whole checkout by default, that contains `pattern` as plain text, case-sensitive, one match per line as `<path>:<line number>:<text>`, files in the order `list` gives and lines in order; at most `SEARCH_LINES_CAP = 100` lines and `SEARCH_BYTES_CAP = 32_000` bytes, then a line `...\t<n> more matches not shown`; a `path` hidden or outside the checkout is the same error as for `read`; files whose bytes are not UTF-8 are skipped; an empty `pattern` is an error. The tool's docstring states the caps. `numbers.json` counts `searches`, in the numbers line too. The role text names the tool: `explore it with `list`, `read` and `search`,` where it said `explore it with `list` and `read`,`, and nothing else in it changes, so its hash becomes `97196fd3f141c915`. The tests in `test_builder.py` whose docstring names this seed define the behaviour: the six tools in the request in the order list, read, search, write, edit, check, then `final_result`.

After the build, by the attended agent: the evaluation set run again with the new tool, and its tokens per request beside the first run's in the version note; the compact map of the checkout waits for what that says.

From the review of the build: the code's own text counts six tools, `reachable only through six tools: list, read, search, write, edit and check` in the module docstring and `the six tools` in `build_agent`'s, with no `five` left in the module docstring.

From the second review, of the tool's walls: a file is read line by line in text mode, never whole, so its line numbers are `read`'s, universal newlines, a form feed inside a line starting no new line. A file larger than `SEARCH_FILE_CAP = 1_000_000` bytes is not searched, like one whose bytes are not UTF-8 or that cannot be read, and the result then ends with `...\t<n> files not searched`, after the matches or after `no matches`; hidden paths are not walked and are not counted. The matches shown are the first in order, so the trailer counts exactly what follows them: the first match that does not fit in the bytes left ends the shown part, and when nothing has been shown yet it is cut to fit and marked, like `read`'s long line, so no match is out of reach. The docstring states the file cap too.
