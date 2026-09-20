---
created: 2026-09-20
type: seed
status: open
summary: A role may name a base_url and the configuration reads one, but no program uses it, so the reviewer role this host already configures cannot run.
value: 5
effort: S
version:
---

## Evidence

2026-09-20, read in the configuration and in the code by the attended agent, immediately after `reviewer.py` was built and before it had ever been run against a real model.

The instance on this host configures two roles. `builder` is `deepseek-flash`. **`reviewer` is `glm-5.3-flash`**, with a key file that exists and no `base_url`.

`instance.py` reads `base_url` -- it is a field of `Role` and `entry.get("base_url")` fills it -- and it is read nowhere else. `builder.py` builds its model as `OpenAIChatModel(model_name, provider=DeepSeekProvider(api_key=key, http_client=...), profile=PROFILE)` and `reviewer.py`, which reuses that shape, does the same. Neither takes the role's `base_url`, and neither takes anything else that would send the request somewhere other than DeepSeek.

So the reviewer as configured would send the model name `glm-5.3-flash` to DeepSeek's endpoint with a GLM key in the header. It has never been run, because goal A of [[reviewer-role]] was finished minutes before this was noticed, and the first real run would have failed on the first request.

Three things follow, and the third is the one that matters.

The field is read and never used, which `AGENTS.md` already describes as a thing this repository does not tolerate: a field needs a consumer. It has had none since v0.15 added it.

`PROFILE` is passed explicitly and is DeepSeek's. A model behind another endpoint is not a DeepSeek V4 and the profile that suppresses the forced-tool-choice hazard for one says nothing true about the other.

And the price is the factory's table, which is DeepSeek's peak rate for `deepseek-flash` and is wrong for anything else. `cost_source` would read `table` and the number would be fiction. [[the-budget-that-counts-files]] makes a run's spend the thing that bounds it -- `SOFT_SPEND` lands the tools and `HARD_SPEND` ends the run -- so a role whose price is wrong is a role whose **bound** is wrong, in whichever direction the real rate differs. A reviewer on a dearer model would run past its ceiling believing it was cheap.

## Idea

A role names where its model is served, and the programs use it.

`base_url` reaches the provider, so a role served elsewhere is reached rather than silently sent to DeepSeek. The profile stops being the program's constant and becomes the role's business: DeepSeek's hazard is DeepSeek's, and a role on another endpoint gets whatever is true of it, or nothing.

The price follows the role too, because the spend ceilings are only as good as the number they read. Either the role names its rate, or the library prices it when it has a row for that model, or a role whose price is not known refuses to run rather than running against a fiction -- and that last option is the honest default, since a bound derived from the wrong rate is worse than no bound at all. What `AGENTS.md` already says of this -- "a role on another model has neither name nor row, and what that costs is the seed that adds it" -- is this seed.

The instrument is already configured. This host holds a `reviewer` role on a different provider with its key in place, so the change is testable the moment it is made, and until it is made that configuration is a trap rather than a deployment.
