## Changed
- builder.py

## Did
- builder.py: registered all six Tool(...) entries in build_agent with sequential=True, so pydantic-ai runs one response's tool calls one at a time in the model's order and each call sees what the prior ones wrote.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
