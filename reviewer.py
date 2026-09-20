#!/usr/bin/env python3
"""The reviewer: several dimensions, each several cold sessions over a delivered tree, together.

    uv run reviewer.py <checkout> <seed>

The checkout is the delivered tree, reachable only through three tools -- `list`, `read` and
`search`, the builder's own, with their walls, their caps and their shapes unchanged -- and the
`final_result` function a report comes back through. It cannot write, edit or check: those tools
are never offered, so a reviewer never becomes a builder and never acquires an interest in finding
less. It builds no container and runs nothing of the project's.

Each pass is given the seed's `## Goal`, read the way the builder reads one out of the head's
commit, the change under review -- the diff from the checkout's head to the commit before it, which
is the build the head is -- and, last, one of `DIMENSIONS`: the fixed goals a pass pursues, each
there because something got past a green check. `PASSES` is the passes each dimension gets, five,
fixed and recorded, and no pass sees what another found -- the same agent is asked afresh, with no
history. A finding carries the dimension that found it, and what two or more passes of one dimension
reached is the report; what one reached alone stays in the record, and the numbers count everything
seen. It runs as the role `reviewer`, whose model and key the instance's configuration names,
exactly as a build runs as the role `builder`.

A review is recorded like a build: a directory of its own in the instance's store, named by its
stamp, holding goal.txt, messages.json, wire.jsonl.gz, review.json, review.md and numbers.json,
with the record's path the first line printed. review.md is the note the review template's shape
gives, for the attended agent to reproduce and judge -- written into the record, never the vault.
The review carries each finding's dimension and the count of passes of that dimension behind it,
how many passes ran, and `agreement`, the share of everything seen that more than one pass reached
-- never a claim that a contract is met. The numbers name the role, its model, the
head it reviewed and the seed it was given. The record is searched for every key the configuration
names before the store takes it, as a build's is, and a record the store would not take is not
committed.

Exit 0 when the model reported, 1 on a cap or a provider error, 2 on what it cannot review: a
directory that is not a checkout git can read, a head with no commit before it to compare against,
an argument that names no seed note, and a seed the head's commit does not hold -- each refused, in
its own words, before a model is called and before a record is made.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import builder
from instance import instance_config, record_store, role as instance_role
from pydantic import BaseModel, Field
from pydantic_ai.models.wrapper import WrapperModel

ROLE = """\
You are the reviewer. You are given a goal and a checkout: a delivered tree and the change under
review. You can explore it with `list`, `read` and `search`, and nothing else: you cannot change
the checkout, and you run nothing of the project's. The goal is what the change was asked to do.

Read the change and the tree it left. For each thing that is wrong, report a finding through the
`final_result` function: the severity, the path it points at, the line of that file, and what is
wrong. Use `defect` when the code does not do what the goal or its tests claim, and `smell` when
it does but the code is worse than it needs to be. Name a path the checkout holds and a line of
that file.

Rules: report only what you read in the tree and the change; a finding that names nothing cannot
be judged. Return an empty list of findings when you find nothing. No commentary outside the
report.
"""


class Finding(BaseModel):
    """One thing the review found: where it is and what is wrong."""

    severity: Literal["defect", "smell"] = Field(
        description="The severity the notes already use: defect or smell."
    )
    path: str = Field(description="The path of the file the finding points at, as the checkout names it.")
    line: int = Field(description="The line of that file the finding points at.")
    what: str = Field(description="What is wrong.")


class ReviewReport(BaseModel):
    """What one pass found: its findings and nothing else."""

    findings: list[Finding] = Field(description="What the review found, one finding each.")


# Five passes, fixed: `PASSES` is the passes each dimension gets and is recorded in its numbers, so
# two reviews are comparable. One reading finds a minority of what is there and five agree on very
# little, which is the point -- what several reached is what the report is made of.
PASSES = 5

# The fixed goals a pass pursues, one per pass, each phrased as a goal rather than a question and
# each there because something got past a green check: a change that met its tests without meeting
# the Goal, a clause of the Goal no test would catch being broken, work the program already does,
# and documentation left describing what is gone. A dimension that catches nothing over the cases
# is dropped, which the catch-rate harness is for. The order is the order they are run in and does
# not matter to what is found; what matters is that each gets `PASSES` passes of its own.
DIMENSIONS = (
    "Find every place the change satisfies its tests without meeting the goal.",
    "Find every claim the goal makes that no test would catch being broken.",
    "Find work the program already does.",
    "Find what now describes something that is gone.",
)


class ReportedFinding(Finding):
    """A finding more than one pass of one dimension reached: where it is, what is wrong, which
    dimension pursued it and how many of that dimension's passes reached it."""

    dimension: str = Field(description="The dimension the passes that found it were pursuing.")
    passes: int = Field(description="How many passes of that dimension reached it, by path and line.")


class Review(BaseModel):
    """What the passes together found and how far they agreed. Never whether the change is
    correct: no number of passes can warrant that, so nothing here says a contract is met."""

    passes: int = Field(description="How many passes ran.")
    matched_by: str = Field(
        description="What makes two findings one: the dimension, the path and the line."
    )
    seen: int = Field(description="Every finding the passes saw, reported or not.")
    agreement: float = Field(
        description="The share of everything seen that more than one pass reached."
    )
    findings: list[ReportedFinding] = Field(
        description="What more than one pass reached, each with the count of passes behind it."
    )


def combine(reports: list[tuple[str, ReviewReport]]) -> Review:
    """The passes made into one answer, each report with the dimension its pass pursued. Two findings
    are one when they name the same dimension and the same path and line -- never their prose,
    because that would need a second model's judgement -- so the measure is crude and the record
    says so. Agreement is counted inside a dimension: two passes asked different questions that
    land on one line found two things, and collapsing them would report agreement that was never
    had. What two or more passes of one dimension reached is reported with its count; what one pass
    reached alone stays out of the report but is still counted in `seen` and in the agreement."""
    counts: dict[tuple[str, str, int], int] = {}
    first: dict[tuple[str, str, int], Finding] = {}
    order: list[tuple[str, str, int]] = []
    for dimension, report in reports:
        named = {(dimension, finding.path, finding.line) for finding in report.findings}
        for finding in report.findings:
            key = (dimension, finding.path, finding.line)
            if key not in first:  # the earliest pass's words stand for the finding
                first[key] = finding
                order.append(key)
        for key in named:
            counts[key] = counts.get(key, 0) + 1
    seen = [
        ReportedFinding(severity=first[key].severity, path=key[1], line=key[2],
                        what=first[key].what, dimension=key[0], passes=counts[key])  # fmt: skip
        for key in order
    ]
    reported = [finding for finding in seen if finding.passes > 1]
    agreement = len(reported) / len(seen) if seen else 0.0
    return Review(
        passes=len(reports), matched_by="dimension, path and line", seen=len(seen),
        agreement=agreement, findings=reported,
    )


def render_note(review: Review) -> str:
    """The review as the note `docs/templates/review.md` gives: a heading per finding with its
    severity and its dimension, ready for the attended agent to move into `docs/reviews/` once they
    have reproduced it. It is written into the record and never the vault, and it fills neither
    `verified` nor `judged` in: those mean the attended agent reproduced the finding and decided
    what it became, and a role that could fill them would be marking its own homework."""
    lines = ["## Findings", ""]
    for finding in review.findings:
        title = " ".join(finding.what.split()) or f"{finding.path}:{finding.line}"
        lines += [
            f"### {title}",
            "",
            f"severity: {finding.severity}",
            f"dimension: {finding.dimension}",
            "",
            finding.what,
            "",
            f"{finding.path}:{finding.line}",
            "",
        ]
    return "\n".join(lines) + "\n"


def usage_error(reason: str = "") -> int:
    print("usage: reviewer.py <checkout> <seed>", file=sys.stderr)
    if reason:
        print(reason, file=sys.stderr)
    return 2


def _tool_definitions(params: Any) -> list[dict[str, Any]]:
    """The tools a request offers, in the shape a provider's request body holds them: the run's own
    three and the output tool its report comes back through, each as a named function."""
    out: list[dict[str, Any]] = []
    for tool in [*params.function_tools, *params.output_tools]:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.parameters_json_schema,
                },
            }
        )
    return out


class WireModel(WrapperModel):
    """A model that records, on the wire, the tools each request offers before it answers. A run
    whose model does not go over HTTP -- a scripted one -- still has the wire say what the model
    was offered, because that is what the wire is for; a run whose model does go over HTTP records
    the request itself, and is not wrapped."""

    def __init__(self, wrapped: Any, wire: builder.Wire):
        super().__init__(wrapped)
        self._wire = wire

    async def request(self, messages: Any, model_settings: Any, model_request_parameters: Any) -> Any:
        self._wire._write(
            dir="request",
            method="POST",
            url="",
            status=None,
            headers={},
            body={"tools": _tool_definitions(model_request_parameters)},
        )
        return await super().request(messages, model_settings, model_request_parameters)


def build_agent(
    tools: builder.Tools, key: str = "", http_client: Any = None,
    model: Any = None, model_name: str = builder.MODEL, base_url: str | None = None,
) -> Any:  # fmt: skip
    """The agent: the reviewer's role, the three tools that read, the typed report and the caps.
    The model is the caller's, or the one `model_name` names -- the instance's `reviewer` role --
    reached at `base_url` when the role names one. `PROFILE` says what DeepSeek's thinking models
    are, so it is passed only for the model it was written for; a model served at another address
    is not one and is given the stock profile."""
    if model is None:
        # The role's address, when it names one, is the client the provider reaches: the stock
        # DeepSeekProvider has no `base_url` of its own, so an OpenAI client built at it is what
        # the provider is handed. `PROFILE` is DeepSeek's, so it is passed only for the model it
        # was written for; a model served elsewhere gets the library's own profile.
        provider = (
            builder.DeepSeekProvider(
                openai_client=builder.AsyncOpenAI(
                    base_url=base_url, api_key=key, http_client=http_client
                )
            )
            if base_url
            else builder.DeepSeekProvider(api_key=key, http_client=http_client)
        )
        model = builder.OpenAIChatModel(
            model_name, provider=provider, profile=None if base_url else builder.PROFILE
        )
    agent = builder.Agent(
        model,
        instructions=ROLE,
        output_type=ReviewReport,
        tools=[
            builder.Tool(tools.list, takes_ctx=False, sequential=True),
            builder.Tool(tools.read, takes_ctx=False, sequential=True),
            builder.Tool(tools.search, takes_ctx=False, sequential=True),
        ],
        model_settings=builder.OpenAIChatModelSettings(timeout=180),
        retries={"tools": 1, "output": 2},
    )
    return agent


def _head_parent(checkout: Path) -> str:
    """The commit before the head: `HEAD^`, empty when the head has no parent to compare against."""
    return builder.git(checkout, "rev-parse", "--verify", "-q", "HEAD^", ok=(0, 1)).strip()


def _review_diff(checkout: Path, parent: str, head: str) -> str:
    """The change under review: the diff from the head to the commit before it. git's own patch,
    with the environment's diff programs and the checkout's attributes unable to replace it."""
    return builder.git(
        checkout, "diff", "--no-ext-diff", "--no-textconv", "--text", parent, head, "--"
    )


def main(argv: list[str], model: Any = None) -> int:
    if len(argv) != 3 or not argv[1].strip() or not argv[2].strip():
        return usage_error()
    checkout = Path(argv[1]).resolve()
    if not checkout.is_dir():
        return usage_error(f"not a directory: {argv[1]}")
    # A checkout is the root of its own repository, and the environment may not point git
    # elsewhere: the same wall the builder's first call makes, in the same words.
    try:
        top = builder.git(checkout, "rev-parse", "--show-toplevel").strip()
    except FileNotFoundError:
        return usage_error(f"git is not available: {argv[1]}")
    except builder.GitError as e:
        refusal = builder.git_refusal(str(e))
        if not refusal.startswith(("not a git repository", "invalid gitfile format")):
            return usage_error(str(e))
        return usage_error(f"not a git checkout: {argv[1]}")
    except (OSError, subprocess.SubprocessError) as e:
        return usage_error(f"git could not run: {e}")
    if not top or Path(top).resolve() != checkout:
        return usage_error(f"not a git checkout: {argv[1]}")
    # The reviewer's second argument is a seed and nothing else, where the builder's may be text:
    # the seed is read the way the builder reads one, its text the head's commit, `git show
    # HEAD:<path>`, and its `## Goal` the goal. An argument `read_seed` takes for text is no seed,
    # and a seed the commit does not hold is refused too, before a model is called.
    try:
        goal, seed = builder.read_seed(checkout, argv[2].strip())
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        return usage_error(str(e))
    if seed is None:  # the argument was read as text: no seed names no goal to review
        return usage_error(f"not a seed: {argv[2]}")
    goal_text = goal.split("\n", 1)[1]
    try:
        checkout_head = builder.head(checkout)
    except (OSError, subprocess.SubprocessError, builder.GitError) as e:
        return usage_error(str(e))
    # A head with no commit before it has no change to review: refused before any record is made.
    try:
        parent = _head_parent(checkout)
    except (OSError, subprocess.SubprocessError, builder.GitError) as e:
        return usage_error(str(e))
    if not parent:
        return usage_error(f"the head has no commit before it to compare against: {argv[1]}")
    try:
        diff = _review_diff(checkout, parent, checkout_head)
    except (OSError, subprocess.SubprocessError, builder.GitError) as e:
        return usage_error(str(e))
    # The store and the role are the instance's: a configuration the run cannot use is a usage
    # error before the key is read, a model called or anything made.
    try:
        config = instance_config()
        store = record_store(checkout)
    except (ValueError, OSError) as e:
        return usage_error(str(e))
    try:
        role = instance_role("reviewer")
    except (ValueError, OSError) as e:
        return usage_error(str(e))
    try:
        key = builder.read_key(role.key)
    except (ValueError, OSError) as e:
        return usage_error(str(e))
    try:
        store.mkdir(parents=True, exist_ok=True)
    except OSError:
        return usage_error(f"{config}: records {store} cannot be made")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir, nth = store / stamp, 1
    while True:  # two reviews in the same second each keep their own record
        try:
            run_dir.mkdir(parents=True)
            break
        except FileExistsError:
            nth += 1
            run_dir = store / f"{stamp}-{nth}"
    (run_dir / "goal.txt").write_text(goal_text + "\n")

    wire = builder.Wire(run_dir / "wire.jsonl")
    # Each pass counts into its own usage, so the library's caps are the pass's own and a second
    # pass is not cut off by the first; every pass's usage is kept, so the record prices them all.
    usages: list[Any] = []  # every pass's usage, in order
    inflight: list[Any] = []  # the pass in flight, so `pass_spent` sees it while it runs

    def one_price(u: Any) -> float:
        """The one function's price for this role's model: the library's row when it has one, the
        table when the model is ours, and the table's arithmetic for a model neither can price, so a
        pass still lands rather than crashing. A caller that replaced `builder.price` with a
        usage-only stand-in is called with the usage alone, which is what its signature takes."""
        try:
            return builder.price(u, role.model)
        except builder.UnknownPrice:
            return builder.table_price(u)
        except TypeError:
            return builder.price(u)

    def cost(seen: list[Any]) -> float:
        """What those usages cost, in the record's own arithmetic: the library's price where it
        names one, the one function's answer for the role's own model otherwise."""
        if seen and all(u.cost is not None for u in seen):
            return sum(float(u.cost) for u in seen)
        return sum(one_price(u) for u in seen)

    def pass_spent() -> float:
        """What the pass in flight has spent: the ceiling is a pass's own, against the same two
        ceilings a build gets, so a review of five passes is not landed on the third pass's first
        tool call because the first two already spent a review's worth."""
        return cost(inflight)

    def review_spent() -> float:
        """What every pass of the review has spent, the one in flight included: the total the
        review's own ceiling is counted in."""
        return cost([*usages, *inflight])

    tools = builder.Tools(checkout, run_dir, spent=pass_spent)
    # A scripted model does not go over HTTP, so it is wrapped to record on the wire what it was
    # offered; a real model's own requests are recorded by the wire's HTTP hooks.
    run_model = None if model is None else WireModel(model, wire)
    agent = build_agent(tools, key=key, http_client=wire.client, model=run_model, model_name=role.model,
                        base_url=role.base_url)  # fmt: skip
    # The shared material first and the dimension last, so every session of the review -- every
    # pass of every dimension -- shares one cached prefix. The dimension is what differs, so it is
    # the tail; getting the order backwards costs real money silently and nothing catches it.
    shared = f"{goal_text}\n\nThe change under review:\n\n{diff}"
    # The review stops starting passes once it has spent what its passes were worth: every
    # dimension's `PASSES` at the soft ceiling, derived from the product rather than from `PASSES`
    # alone, or it shrinks by a quarter the moment a fourth dimension is added. A pass may run to
    # `HARD_SPEND`, above the ceiling the total is counted in, so a review of runaway passes ends
    # early and one of ordinary passes never reaches it. What it must not do is kill a pass already
    # running: it decides whether to start the next one, and the passes that already answered are
    # what the review has.
    ceiling = len(DIMENSIONS) * PASSES * builder.SOFT_SPEND
    t0 = time.time()
    # Every dimension gets `PASSES` cold sessions over the same checkout, goal and diff. No pass
    # sees another's messages: the same agent is asked afresh, with no history, so nothing one pass
    # found reaches the next, and agreement counted inside a dimension is agreement really had.
    reports: list[tuple[str, ReviewReport]] = []
    messages: list[Any] = []
    stopped, detail = "answer", ""
    stop = False
    for dimension in DIMENSIONS:
        if stop:
            break
        for _ in range(PASSES):
            tools.calls = 0  # a cold session reads on its own count, not the passes' before it
            usage = builder.RunUsage()
            inflight.append(usage)  # the one in flight: `pass_spent` sees it while it runs
            prompt = f"{shared}\n\n{dimension}"
            report, answered, _, stopped, detail = builder.run(agent, prompt, usage=usage)
            inflight.pop()
            usages.append(usage)
            messages.extend(answered)
            if report is not None:
                reports.append((dimension, report))
            # A pass that did not answer ends the review, and so does one that leaves it having
            # spent what its passes were worth; both decide whether to start the next pass.
            if stopped != "answer" or review_spent() >= ceiling:
                stop = True
                break
    seconds = round(time.time() - t0, 1)

    review = combine(reports)
    (run_dir / "messages.json").write_bytes(builder.ModelMessagesTypeAdapter.dump_json(messages, indent=1))
    # The passes that answered are the review, however the run ended: a review capped after some
    # passes answered still writes what they found, as a capped build's tree is still its work.
    # A review no pass answered has nothing to say and writes no report. The note beside the report
    # is the shape the template gives, for the attended agent to reproduce and judge -- the
    # reviewer fills none of `verified` or `judged` in, because a role that could would be marking
    # its own homework.
    if reports:
        (run_dir / "review.json").write_text(review.model_dump_json(indent=1) + "\n")
        (run_dir / "review.md").write_text(render_note(review))
    priced = bool(usages) and all(u.cost is not None for u in usages)
    cost_usd = round(sum(float(u.cost) if priced else one_price(u) for u in usages), 5)
    cost_source = "table" if role.model == builder.MODEL else "genai-prices"
    numbers = {
        "role_name": "reviewer",
        "role": builder.sha256(ROLE),
        "wrapper": builder.sha256(Path(__file__).read_text()),
        "library": builder.LIBRARY,
        "model": role.model,
        "checkout": str(checkout),
        "head": checkout_head,
        "seed": seed,
        "stopped": stopped,
        "cap": builder.which_cap(stopped, detail),
        "dimensions": len(DIMENSIONS),
        "passes": PASSES,
        "passes_ran": len(reports),
        "requests": sum(u.requests for u in usages),
        "requests_cap": builder.limits().request_limit,
        "wire_attempts": wire.attempts,
        "tool_calls": sum(u.tool_calls for u in usages),
        "calls_cap": builder.CALLS_LIMIT,
        "input_tokens": sum(u.input_tokens for u in usages),
        "output_tokens": sum(u.output_tokens for u in usages),
        "cache_read_tokens": sum(u.cache_read_tokens for u in usages),
        "reasoning_tokens": sum(u.details.get("reasoning_tokens", 0) for u in usages),
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        "spend_cap": builder.SOFT_SPEND,
        "hard_spend_cap": builder.HARD_SPEND,
        "lists": len(tools.listed),
        "reads": len(tools.read_paths),
        "files_read": len(set(tools.read_paths)),
        "lines_read": tools.lines_read,
        "searches": len(tools.searched),
        "findings": len(review.findings),
        "findings_seen": review.seen,
        "findings_reported": len(review.findings),
        "agreement": review.agreement,
        "seconds": seconds,
    }
    recorded = numbers | {"detail": detail} if detail else numbers  # why it stopped, if not answer
    (run_dir / "numbers.json").write_text(json.dumps(recorded, indent=1) + "\n")
    # The record is the factory's: the wire is compressed and the whole record searched for every
    # key the instance's configuration names by the one function that commits it.
    builder.compress_wire(run_dir)
    print(run_dir)  # the first line the reviewer prints is the record's path
    numbers_line = " ".join(f"{k}={v}" for k, v in numbers.items())  # stays one line of k=v
    try:
        builder.commit_record(store, run_dir)
    except builder.LeakedKey as e:
        print(numbers_line)
        print(f"{e}: the record holds the key", file=sys.stderr)  # never the value
        return 1
    except (builder.GitError, OSError, subprocess.SubprocessError) as e:
        print(numbers_line)
        print(f"{run_dir}: {' '.join(str(e).split())}", file=sys.stderr)
        return 1
    print(numbers_line)
    if detail:
        print(f"{stopped}: {detail}", file=sys.stderr)
    return 0 if stopped == "answer" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
