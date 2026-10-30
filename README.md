# Supplier Acknowledgement, Promise-Date & Schedule-Impact Dataset

Synthetic, fully reproducible data for the workflow *manage supplier acknowledgements, promised dates, quantity changes and downstream schedule impacts*.
Planner / supplier / warehouse-operator / logistics-analyst / ops-manager actors are modelled (carriers are out of scope; inbound notices go to the warehouse operator).

| | |
|---|---|
| Fixed seed | `20261022` |
| Full command | `python generate_data.py --seed 20261022 --scale 1.0 --out data_full` |
| Starter command (same generator) | `python generate_data.py --seed 20261022 --scale 0.05 --out data_starter` |
| Whole pipeline | `./run_all.sh` (generate → validate → SQL export → reproducibility check, ~25 s, Python 3 stdlib only) |
| As-of snapshot | 2026-10-22 18:00 (statuses such as `PENDING_APPROVAL` are relative to this instant) |
| External data | None. See `source_manifest.json` |

## Volume (data_full, scale 1.0)
10,000 POs · 23,864 PO lines · **15,000 acknowledgement revisions** (exact target) · 35,807 promise rows · 13,881 change requests · 15,320 approval steps · 34,910 plan versions · 16,698 production orders · 20,294 supply links · 4,489 impact rows · 26,006 notifications · 35,628 PO status events · 190 ground-truth anomalies.
"15,000 acknowledgement/change events" is implemented as 15,000 acknowledgement revisions (each one a supplier event); the change requests they spawn are additional derived events. Both counts scale with `--scale` (`n_po = 10000*scale`, `acks = 1.5*n_po`).

## Entities, keys and cardinality
`Supplier 1:N PurchaseOrder 1:N POLine` · `PurchaseOrder 1:N Acknowledgement` (one row per **revision**, never overwritten; `supersedes_ack_id` chains them) ·
`Acknowledgement N:M POLine` resolved by bridge **PromiseDate** (accepted/rejected qty, promised date, price per line per revision) ·
`PromiseDate → ChangeRequest` (one per changed value: DATE / QTY / PRICE) · `ChangeRequest 1:N Approval` (≤2 steps) · `ChangeRequest N:M ProductionOrder` via **ChangeImpact** ·
`ProductionOrder N:M POLine` via bridge **ProductionOrderSupply** · `POLine 1:N InventoryPlan` (append-only versions, effective-dated, `source_change_id` optional) ·
`Notification` → user / PO / change / production order (change and production order optional) · `POStatusHistory` (append-only lifecycle) · reference tables `ApprovalThreshold`, `AppUser`, `Warehouse`, `Item`.
Every field (type, required, allowed values, unit, uniqueness, validation rule, FK) is in `data_dictionary.csv`; DDL with PK/FK/enum CHECKs is generated from the same definition (`schema.sql`).

IDs: `PO-2026-000001`, `ACK-<PO-id>-01`, `CHG-<PO-id>-000001` (counter per PO), `APR-<change-id>-01`, `NOT-2026-000001` as specified; plus `PRM-<ack-id>-L01`, `PLN-2026-000001`, `PRD-2026-000001`, `PSL-/IMP-/PSE-nnnnnn`. Zero-padded, immutable, consistent across files.

## Business rules implemented (all outcomes derive from these, not independent randomness)
* **Supplier behaviour** is driven by reliability tier A/B/C (silence 2/6/14 %, date slips, partial acceptance, rejections, price moves, revision propensity). Silent POs have no acknowledgement; slow suppliers breach the SLA and acknowledge late.
* **Revisions** re-state every line; each revision is compared with the previous proposal; thresholds are always evaluated against the **requested** PO-line value.
* **Thresholds** (`ApprovalThreshold.csv`): date |Δ| ≤3 d auto, ≤14 d planner, >14 d manager; qty shortfall ≤5 % auto, ≤20 % planner, >20 % manager; price |Δ| ≤2 % auto, ≤10 % planner, >10 % manager; any line-value move > USD 50k escalates to manager; promised date before PO order date is rejected by the system (`THR-SAN-1`). Manager level = planner endorsement (step 1) then ops manager (step 2).
* **Decisions**: planner rejects if a HIGH-priority production order would be >7 days late or short, or price increase >7 %; ops manager rejects if impact exists and (tier C supplier, >30 days late, or >50 % shortage) or price increase >15 %. A newer revision arriving before a decision marks the open change `SUPERSEDED`; ~4 % of approvals stall (long-tail delay) and some remain `PENDING_APPROVAL`.
* **Projected supply** (`InventoryPlan`) gets a new version only when a DATE/QTY change is `APPROVED`/`AUTO_APPROVED`, effective at the final approval time. Rejected, pending and superseded changes never touch it.
* **Downstream impact** is computed per supply link (late supply / short supply, with FIFO allocation of ordered qty across production orders) → `ChangeImpact`; on approval, `SCHEDULE_IMPACT` notifications go to the production-order owner planner (and a logistics analyst when priority is HIGH), `INBOUND_RESCHEDULE` to the warehouse operator; also `APPROVAL_REQUIRED`, `CHANGE_REJECTED`, `SUPPLIER_SILENCE`.
* **Statuses** (ack, line, PO, production order) are derived from source records; PO transitions are stored in `POStatusHistory`.

## Injected edge cases and ground truth
Baseline records are generated clean first, then labelled anomalies are injected; no unrelated rows are altered. Labels are **only** in `ground_truth.csv/json` (id, issue type, record id, related ids, detection rule, expected decision) and are not columns in any input table.

| issue_type | count | injected as | expected decision |
|---|---|---|---|
| `ACK_REFERS_WRONG_PO_LINE` | 50 | extra promise row (`-X01`) on an ack pointing to a line of another PO | quarantine row |
| `PROMISE_DATE_BEFORE_ORDER_DATE` | 50 | promised date set 1–20 d before PO order date (ack status re-derived; change auto-rejected by `THR-SAN-1`) | reject change |
| `UNAPPROVED_CHANGE_UPDATES_INVENTORY_PLAN` | 50 | plan version sourced from a rejected/pending change | block plan update |
| `OLDER_REVISION_OVERWRITES_NEWER` | 40 | plan version re-applying an older revision after a newer one | reject stale revision |

## Validation (`validation_summary.md/json`)
53/53 checks pass on full and starter sets: PK uniqueness and enums (load constraints), FK integrity for all tables, ID formats, date ordering, qty/value/total reconciliation, derived-delta recomputation, threshold ↔ level consistency, ack/line/PO status consistency, approval-trail ↔ change-status lifecycle, supersession logic, duplicate checks, plan ↔ approved-change reconciliation (excluding labelled lines), impact → notification coverage, and four detection rules that flag **exactly** the ground-truth rows (precision = recall = 1.0 for each). The validators were mutation-tested (corrupting quantities, statuses, FKs, totals and plan timestamps is detected).

Profile highlights (full): ack status – 46 % accepted-with-changes, 35 % accepted, 20 % partial, 0.2 % rejected; 62.5 % of POs have 1 ack, 16 % 2, 6.7 % 3, remainder 4–6; 723 POs with no acknowledgement (silence rate A 1.6 % / B 5.9 % / C 14.3 %); changes: 9,493 date, 3,032 qty, 1,356 price; 45 % auto-approved, 43 % approved by humans, 7 % rejected, 5 % superseded, 14 still pending; 3,756 changes with downstream impact.

## Reproducibility
`check_reproducibility.py` regenerates twice with the same seed/scale and compares per-file row counts and SHA-256 hashes against the delivered files → `reproducibility_check.json` (`identical: true`, 21 files, both datasets). No wall-clock values or hash-order dependence in the generator.

## Provenance / lawful use
No external datasets, scraping or personal data. Names and countries come from small hard-coded lists; all values are generated by `random.Random(seed)`. Public ERP/EDI PO-acknowledgement conventions were used for schema inspiration only.

## Files
`data_full/` and `data_starter/`: 17 entity CSVs, `ground_truth.csv/.json`, `schema.sql`, `seed_data.sql(.gz)` (FK-safe order), `data_dictionary.csv`, `source_manifest.json`, `checksums.json`, `validation_summary.*`, `reproducibility_check.json`.
Code: `generate_data.py`, `schema_def.py`, `validate_data.py`, `export_sql.py`, `check_reproducibility.py`, `run_all.sh`.

## Known simplifications
Calendar (not business) hours for SLAs/approvals; single currency (USD); price changes do not alter the supply plan (cost only); ack quantity totals mix UoMs; each revision restates all lines; carriers are not a modelled entity.
