## Changed
- builder.py

## Did
- builder.py: added Wire._body, a static helper that returns json.loads(text) and falls back to the raw text on ValueError, so a body that parses as JSON is recorded as the parsed value and anything else stays the text it was.
- builder.py: on_request now records body=self._body(body) instead of body=body, so a JSON request body lands in wire.jsonl as parsed JSON.
- builder.py: on_response now records body=self._body(response.text) instead of body=response.text, so a JSON response body lands in wire.jsonl as parsed JSON.
- builder.py: header redaction (_headers) and the rest of Wire are untouched, so no secret-bearing header behaviour changed and the JSON bodies carry no key.

## Check
- green

## Failing
- (none)

## Unsure
- Whether README.md's description of wire.jsonl bodies should also be updated; it says only 'full bodies' and is not covered by the tests, so I left it unchanged.
- json.loads also accepts bare scalars (e.g. '123', 'true', 'null'), which are now recorded as those values rather than text; the tests only cover object JSON bodies, so this reading of 'parses as JSON' is unverified beyond the suite.
