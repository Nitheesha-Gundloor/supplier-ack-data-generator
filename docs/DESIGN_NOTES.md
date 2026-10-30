# Design notes

## Problem
Produce a reproducible synthetic dataset for the supplier-acknowledgement workflow: acknowledgements -> promised dates / qty / price changes -> approval thresholds -> projected-supply updates only after approval -> downstream production impact -> planner notifications, with labelled anomalies and an answer key.

## Key assumptions
* The deliverable is **data plus generator plus validation**, not an application. "Medium complexity" is met by 17 related tables, conditional rules, exception paths and measurable validation/detection metrics.
* As-of date is 2026-10-22 18:00 (the fixed-seed date in the brief); statuses are snapshots at that instant.
* "15,000 acknowledgement/change events" = 15,000 acknowledgement revisions; change requests are derived on top (13,881).
* Thresholds and decision rules are my assumptions (see README); they are parameters in code and the `ApprovalThreshold` table.

## Key decisions and trade-offs
| Decision | Why | Trade-off |
|---|---|---|
| Append-only versions (ack revisions, plan versions, status history) | Brief: "do not overwrite history" | More rows |
| `PromiseDate` as bridge Ack N:M POLine | Brief: bridge tables for N:M | Extra join |
| Outcomes derived from rules (thresholds, impact, status) | Brief: not independent random assignment | Randomness only in timing/behaviour inputs |
| Anomalies injected after clean baseline; labels only in `ground_truth.*` | Prevent leakage, keep unrelated rows intact | Injected rows still flow through derivations (e.g. ack status is re-derived) |
| Single schema definition (`schema_def.py`) generates dictionary and DDL | No drift between docs and schema | Slightly indirect |
| Python stdlib only, SQLite for validation | Runs anywhere, no installs | Not a production DB |
| Only `random.Random(seed)`, no wall-clock, no set/hash ordering | Byte-identical regeneration | - |

## Testing approach
1. Load CSVs into SQLite with PK/FK/enum CHECK constraints (`validate_data.py`).
2. 53 checks: FK integrity, ID formats, date ordering, arithmetic reconciliation, threshold<->level, status derivation, approval lifecycle, supersession, duplicates, plan<->approved-change reconciliation, impact->notification coverage.
3. Four anomaly-detection SQL rules compared with `ground_truth.csv` (precision = recall = 1.0).
4. Mutation tests: corrupted copies (qty, status, FK, totals, plan timestamp) were detected.
5. Reproducibility: regenerate twice, compare row counts and SHA-256 (`reproducibility_check.json`).

## Limitations / next steps
Calendar hours instead of business hours; single currency; price changes do not alter the plan; quantity totals mix units of measure; each revision restates all lines; carriers are not an entity; distributions not calibrated to real data; the ground-truth rule detectors are SQL equivalents of the injection logic (so perfect scores show consistency, not generalisation). Next: realistic calendars, partial-line revisions, an ML detector evaluated against the answer key.
