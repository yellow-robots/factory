## Changed
- builder.py

## Did
- builder.py: in Tools.list, entries are now named by their path relative to the checkout root (`sub/b.txt`), not their bare basename, except at the root itself, which stays `a.txt`; this satisfies the seed's 'a listing keeps naming its entries by their path relative to the checkout root' and also makes the `sub/.git` omission test meaningful.

## Check
- green

## Failing
- (none)

## Unsure
- The other record-hardening behaviours (refusing a `.git` component at any depth as `not part of the checkout`, `--text` in record_diff, LC_ALL=C in git_env, the first-`fatal:`-line not-a-checkout test, the `written`/`edited` numbers keys and line, the protected refusal wording, and the check.Dockerfile comments) were already present in builder.py and are covered by the now-green suite; I did not otherwise verify them by hand outside the tests.
