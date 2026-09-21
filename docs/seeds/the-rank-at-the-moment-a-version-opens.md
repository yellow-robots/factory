---
created: 2026-09-21
type: seed
status: open
summary: The backlog ranks a seed by a tier written the day it was filed and an effort guessed then, so what is highest when a version opens is that day's perception; git, the store and the vault hold what the last version cost, what each seed unblocks and whether its evidence still holds, and a command prints the rank from them.
value: 4
effort: M
reporter: owner
kind: measurement
version:
---

## Evidence

2026-09-21, at 7eb06ed, by the owner with the attended agent, at the opening of v0.22. `docs/backlog.base` ranks by `value - (S 0, M 0.5, L 1)`, and `docs/templates/seed.md` defines value as a tier by kind -- 5 autonomy or a wall, 4 a measure, 3 a step, 2 cost, 1 convenience -- so the rank says what a seed is and not how much it moves, and it says it once.

The day v0.21 shipped: 20 builds, $1.96 at the flat rate, 9 of them red at the soft cap for $1.31 -- two thirds of the day's spend on runs that read and never wrote. The seed naming that, [[the-read-that-costs-a-request]], was a 4 since 2026-09-19 and nothing in the backlog rose. An audit of the 35 open seeds against HEAD moved nine labels: five efforts (analyst-on-api-models M to L, credentials-the-tools-should-not-read M to S, the-diff-and-what-it-made-load-bearing M to S, the-table-that-bills-twice M to S, paired-set-runs M to L or S by its form), three values (walls-in-the-numbers 4 to 3, the-import-nobody-declared 2 to 3, the-table-that-bills-twice 3 to 2), and one moot (one-walk-for-what-the-tools-can-reach, its walk removed at v0.20); each drift a line number, a count, a constant changed by hand, or a structure added or removed since the seed was born. [[set-world-outside-the-repository]] is named as prerequisite by three open seeds, the-read-that-costs-a-request by three, [[the-constants-that-answer-for-nothing]] by two, and the backlog shows none of it. [[the-loop-in-numbers]] is the reader that would print the first of these numbers; it is v0.22's.

The owner's rule on the day: the backlog is the owner's and a commissioner never shares one. So this is a command of the loop like `next`, beside the gate and outside the wheel, and the product -- builder, build, reviewer -- reads no backlog and knows nothing of this.

## Idea

`uv run gate.py rank` prints the open seeds in the order to open a version with, derived and never written: the leak of the last version first, from the-loop-in-numbers' table -- money and builds lost to caps, red checks and dead runs -- and the seeds whose kind and Evidence name it; then what each seed unblocks, the open seeds whose notes link to it; then whether its evidence still holds, the files and names its Evidence cites and whether a version since touched them; for integrity seeds, exposure, the records through the hole per version; an autonomy seed after its measurement seed; and effort from the reference class, what seeds in the same files cost in the store. The tier written on the seed is the tiebreak among what none of these separates, and every row says why it ranks where it does, which the tier never said. It reads the vault by its templates, the store by its records and git by its trailers, names nothing of this repository, and is verified on the gate tests' fixture vault and a fixture store. Imperfect is fine: an agent asks it for the next set of seeds and reads the reasons.
