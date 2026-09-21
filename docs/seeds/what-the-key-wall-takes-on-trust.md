---
created: 2026-09-19
type: seed
status: open
summary: The wall proves a record holds none of the keys the configuration names, and takes three things on trust: that the key it searches for is the key the run used, that redaction worked, and that a file's name says what its bytes are.
value: 4
effort: M
reporter: research
kind: integrity
version:
---

## Evidence

2026-09-19, from research the owner commissioned into whether an established secret-detection tool should replace the exact search, and reproduced by the attended agent before it was written here.

The survey's answer is that the search should stay. Against a benchmark of nine tools over 818 repositories and 15,084 hand-labelled secrets (Basak et al., ESEM 2023, https://arxiv.org/abs/2307.00714), five of the nine score under 7% precision; the best F1 is gitleaks at 60%; and the paper's conclusion is that "no current tool has the coveted high precision and high recall scores". The cause it names is "generic regular expressions and ineffective entropy calculation", with a worked example of a real secret scoring 4.08 against the literal string `ThisIsAReallyLongString` at 4.11. The same inversion holds in this factory's own artefact: the key's Shannon entropy is 3.679 while the pydantic-ai tool-call identifiers beside it in the same wire log score 4.39, and of 55,261 charset-only strings in one real `wire.jsonl`, 4,990 are more random than the key. No entropy threshold separates them. What rescues precision in the benchmark is live credential verification, which lifts one tool from 6% to 90% -- and which means sending candidate secrets to a third party over the network, the one thing this wall exists to prevent. Put against a real record with its redaction disabled, gitleaks, TruffleHog and detect-secrets in their default configurations each found nothing and the exact search refused the commit in 30 milliseconds. Searching an artefact for the literal values of credentials one holds is also a shipped feature of AWS's own `git-secrets`, not an improvisation.

What the survey found instead are three things the wall takes on trust. Each was reproduced here.

The first is the key itself. `main` reads the run's key once at startup from the file the `builder` role names, and passes `key=None` to `commit_record`, which then asks `configured_keys()` for the needles -- reading the configuration and the key files again, at commit time. A key rotated while a run is in flight leaves the record holding the old value and the wall hunting for the new one, and the commit succeeds. Runs last minutes. Established by reading `builder.py` from the startup read to the commit, and by reading `test_keys.py`, whose five tests pin that every configured key is searched for and none of which covers a key that changed between the two.

The second is redaction. `Wire._headers` substitutes `<redacted>` for five header names as the wire is written, and that substitution is the thing the wall exists because it can fail. Yet the only consequence the wall checks for is the narrow case where the leaked value happens to be a string the configuration already names. A second provider's key the configuration does not name, a proxy's `Proxy-Authorization`, a `Set-Cookie` the provider returned, or the rotated key above, all pass. Reproduced: `commit_record` contains no reference to `redacted` at all. As a rule it measures cleanly -- a match on any of the five header names whose value is not exactly `<redacted>` gives 0 findings on an untouched record and 232 on the same record with redaction disabled, with no threshold and no false positives by construction.

The third is the name of a file. `_read_through` decides how to read a record file from `path.name.lower().endswith(".gz")`, so anything compressed under another name is read as the opaque bytes it is, the needle is absent, and the record is committed. Reproduced against this code with a synthetic key in an 800-line payload: `plain.jsonl` caught, `wire.jsonl.gz` caught, `wire.jsonl.GZ` caught, and `wire.jsonl.gzip`, `wire.jsonl.bz2` and a plainly-named `wire.jsonl` holding gzip bytes all **missed**. The sharpest of those is the first: the same compression the code already knows how to read, under a name it does not recognise, walking past the wall in silence. Latent rather than live, since `compress_wire` is the only writer of a compressed file in a record and it writes `wire.jsonl.gz` -- but one line of a future change away, with no error and no signal that the check stopped working. The docstring already claims the dispatch is on the magic and not the name.

A caution for the spec, from the same reading. `commit_record`'s `key` parameter means *instead of* the configuration, and `test_a_caller_that_names_the_key_itself_is_searched_for_that_one` pins that. Adding the run's key to the needles by editing that parameter will break a pinned test and change the older records-only path; it wants either a parameter of its own or a deliberately widened contract with the test amended first, stated as an amendment.

## Idea

Three changes, all before `git add`, all refusing the commit, all naming the path and never a value, all refusing when they cannot complete.

The needles are the keys the configuration names **and** the key the run actually used, deduplicated, so a rotation mid-run cannot open a window.

The redaction invariant is asserted as a second wall: over the wire's decompressed bytes, every value of a header in `SECRET_HEADERS` is exactly `<redacted>`, and anything else refuses the commit. It needs no ruleset, no threshold and no dependency, and it is the honest generalisation of the first wall -- it asserts a property the factory controls rather than guessing at a property it does not, and it is the only one of the three that catches a key the configuration never named.

A record file is read by its leading bytes rather than its name -- gzip, bzip2, xz, zstd and zip each have a magic number -- and a file whose bytes cannot be accounted for as text or as a known compression refuses the commit. The rule becomes "refuse what you cannot read correctly" rather than "refuse what you cannot read", which closes the other half of the fail-open class [[the-search-that-answers-for-no-keys]] opened.

An advisory layer for credentials the factory does not hold is worth its own record field and is not worth gating on: gitleaks is the one tool of the nine that is MIT, makes no network call of any kind, and has the best recall, and across this store's 189 records it found nothing at all. Its value is prospective, about repositories not yet built, and the better control for that risk is not here -- see [[credentials-the-tools-should-not-read]].
