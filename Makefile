# Self-documenting: `make` lists the targets. Every line with `## text` after a target is help.
.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

UV ?= uv
RUN := $(UV) run

.PHONY: help setup test check next changelog

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install the toolchain (uv sync)
	$(UV) sync

test: ## Run the test suite; position tests count as expected failures
	$(RUN) pytest -q

check: ## Lint and format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

next: ## Show the position: current version, next declared version, and the red tests as they really fail
	@echo "version:  $$(git describe --tags --always --dirty)"
	@next=""; for f in $$(ls versions/*.toml 2>/dev/null | sort -V); do v=$$(basename $$f .toml); \
	  if [ -z "$$(git tag -l "v$$v")" ]; then next=$$v; break; fi; done; \
	  echo "next:     $${next:-none declared}"; \
	  if [ -n "$$next" ]; then sed -n 's/^goal = "\(.*\)"$$/goal:     \1/p' versions/$$next.toml; fi
	@echo "red tests:"
	@$(RUN) pytest -q -m next --runxfail -p no:cacheprovider 2>&1 | tail -n 30 || true

changelog: ## Regenerate CHANGELOG.md from conventional commits (git-cliff)
	$(RUN) git-cliff --output CHANGELOG.md
