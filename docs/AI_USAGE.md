# AI usage disclosure

**Tool:** Claude (Anthropic) via claude.ai chat. No other AI tools were used.

## Where AI did the work (heavy reliance)
Nearly all of the implementation was produced by Claude from the project brief in `PROMPT_HISTORY.md`:
* the entity model, data dictionary and DDL (`schema_def.py`),
* the generator (`generate_data.py`) including supplier behaviour, approval workflow, plan versioning, impact calculation and anomaly injection,
* the validator (`validate_data.py`, 53 checks), SQL export, reproducibility checker and `run_all.sh`,
* README and design notes.
Claude also ran the code in its own sandbox, found and fixed bugs (quadratic loops that made the full run time out; an acknowledgement-status inconsistency caused by an injected anomaly; a validator crash on FK-violating input), tuned distributions (fewer partial acceptances, a revision-count tail), and mutation-tested the validators.

## What I personally did
> **[CANDIDATE: complete this section truthfully before submitting. Delete anything that is not true.]**
> Suggested, only if you really did them:
> * Read `generate_data.py` end to end and can explain each phase.
> * Ran `./run_all.sh` myself and saw 53/53 checks and `reproducible: True`.
> * Opened the CSVs and traced one PO through Acknowledgement -> PromiseDate -> ChangeRequest -> Approval -> InventoryPlan -> Notification.
> * Changed something (e.g. a threshold in `level_for`, a probability in `TIER`) and re-ran to see the effect.
> * Decisions I made or overrode: ...

## Decisions the AI made that I must own
The brief asks for "approval thresholds" and "decision rules" without values, so these are **assumptions chosen by the AI**, documented in `README.md` and `DESIGN_NOTES.md`: threshold bands (3/14 days, 5/20 % qty, 2/10 % price, USD 50k escalation), the planner/manager decision rules, supplier-tier behaviour probabilities, the number of anomalies (about 0.4-0.5 % of POs each), and reading "15,000 acknowledgement/change events" as 15,000 acknowledgement revisions.

## Known limits of my verification
Distributions are plausible by construction and checked by profile, not calibrated against real procurement data. Automated checks verify internal consistency; they cannot prove the business rules match any real company's policy.
