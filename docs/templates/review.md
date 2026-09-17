---
created: "{{date}}"
type: review
runs:
reviewer:
---
%%
One note per review, named after the first record it covers: docs/reviews/<stamp>.md.
runs: the records reviewed, their stamps separated by spaces, each a directory runs/<stamp> of the repository. reviewer: who read the diff, the model and where it ran. created: the date, YYYY-MM-DD, filled by the template.
One finding per level-three heading under Findings, its title the heading. Under it, three lines the gate reads: severity, defect or smell; verified, yes or no, yes only once the attended agent reproduced it; judged, what the finding became: test <name>, case <name> or seed <name>, several separated by commas, or none: with the reason. A finding verified yes needs a judgement; one verified no needs none. The prose is what happens and how it was reproduced.
A test named is a test method or class in a test*.py at the root; a case, a directory under cases/; a seed, a note under seeds/.
%%

## Findings

### Title

severity:
verified:
judged:
