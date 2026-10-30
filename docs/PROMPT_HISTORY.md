# Prompt History

## Scope and method
* **AI tool:** Claude (Anthropic), claude.ai web chat. No other AI tool was used.
* **Sessions:** a single conversation. Prompts are listed **verbatim and in chronological order**; none were omitted or edited.
* **Responses:** not reproduced (optional per the submission FAQ). `AI_USAGE.md` describes what the responses contributed.
* **Limitation:** the chat interface offers no machine-readable export, so this file is a manual transcript of my messages.
* **Observation:** the implementation was driven by one comprehensive prompt (the project brief). The remaining prompts were clarification and submission-preparation requests. The iterative refinement (bug fixes, tuning, validation) happened inside the AI's single response to the brief, not through further prompts from me.

## Summary
| # | Type | Purpose | Outcome |
|---|---|---|---|
| 1 | Specification | Provide the full project brief | Generator, schema, validators, SQL export, reproducibility check, README |
| 2 | Clarification | Obtain an overview of the project | High-level explanation of the workflow and deliverable |
| 3 | Clarification | Request a simpler explanation | Plain-language walkthrough with an analogy |
| 4 | Submission | Ask how to submit | Checklist of deliverables and run steps |
| 5 | Submission | Share YottaFlex submission guidelines and FAQ | Added `docs/` (prompt history, AI-usage disclosure, design notes) |
| 6 | Documentation | Ask to restyle this file | Declined to alter or omit prompts; restructured presentation only |

---

## Prompt 1 - Project specification
*Input: project brief pasted as text, no additional instruction.*

```
Business Context / Problem
Manage supplier acknowledgements, promised dates, quantity changes and downstream schedule impacts.

Objective and Scope
Build a working solution for this end-to-end workflow: Manage supplier acknowledgements, promised dates, quantity changes and downstream schedule impacts. The solution should expose key decisions and exceptions, preserve traceability, and produce measurable outputs. Medium complexity means multiple related entities, conditional rules, at least one exception path and meaningful evaluation metrics.

Primary Actors / Systems
Supplier, planner, carrier/warehouse operator, logistics analyst and operations manager

Business Workflow and Rules
1. Generate/reference master data first: Supplier, PurchaseOrder, POLine, Acknowledgement, PromiseDate.
2. Generate dependent transaction/event records using valid parent IDs.
3. Apply business logic: Create POs and lines; generate acknowledgements with accepted/rejected quantities and promised dates; compare changes with requested values; apply approval thresholds for price/date/quantity changes; update projected supply only after approval; notify affected planners.
4. Persist state changes as explicit records/events where relevant; do not overwrite history.
5. Generate outcomes and ground-truth labels from documented rules, not independent random assignment.

Entities and Relationships
Core entities: Supplier, PurchaseOrder, POLine, Acknowledgement, PromiseDate, ChangeRequest, Approval, InventoryPlan, ProductionOrder, Notification. Define a primary key for every entity and foreign keys for every relationship. Document cardinality (1:1, 1:N, N:M), optional relationships, effective dates and lifecycle states. Use bridge tables for many-to-many relationships; retain event history for state changes; validate all joins. For deliberate anomaly cases, keep an issue_type/ground_truth label rather than silently corrupting unrelated rows.

ID / Nomenclature Conventions
PO-2026-000001; ACK-<PO-id>-01; CHG-<PO-id>-000001; APR-<change-id>-01; NOT-2026-000001.

Synthetic Data Generation Instructions (Granular)
Step 1 - Write a data dictionary for: Supplier, PurchaseOrder, POLine, Acknowledgement, PromiseDate, ChangeRequest, Approval, InventoryPlan, ProductionOrder, Notification. For each field specify type, required/optional, allowed values, units, uniqueness and validation rule.
Step 2 - Create parent/master tables first, then child and event tables. Apply this domain-specific generation logic: Create POs and lines; generate acknowledgements with accepted/rejected quantities and promised dates; compare changes with requested values; apply approval thresholds for price/date/quantity changes; update projected supply only after approval; notify affected planners.
Step 3 - Apply deterministic IDs and naming: PO-2026-000001; ACK-<PO-id>-01; CHG-<PO-id>-000001; APR-<change-id>-01; NOT-2026-000001. Keep counters zero-padded, IDs immutable, and referenced IDs exactly consistent across files.
Step 4 - Generate the baseline volume: Generate 10,000 POs and 15,000 acknowledgement/change events. Include partial acceptance, date slips, price changes, supplier silence and multiple revisions. Use a fixed seed (e.g. 20261022) and parameterize scale so starter and full datasets use the same generator.
Step 5 - Generate valid baseline records first, then inject labelled edge cases: Unapproved change updates inventory plan; acknowledgement refers to wrong PO line; promised date before order date; older revision overwrites newer revision.
Step 6 - Calculate derived values (totals, balances, scores, statuses and dates) from source records rather than generating them independently.
Step 7 - Produce a separate ground_truth.csv/json for known anomalies, expected decisions or labels; never leak it into input features.
Step 8 - Run validation: primary-key uniqueness, foreign-key integrity, allowed enums, date ordering, arithmetic reconciliation, lifecycle transitions and duplicate checks.
Step 9 - Export CSV/JSON/SQL seed data plus README, schema/data dictionary, generator command, fixed seed, source manifest and validation summary.
Step 10 - Regenerate twice with the same seed and compare row counts/checksums to demonstrate reproducibility.

Suggested Volume and Coverage
Generate 10,000 POs and 15,000 acknowledgement/change events. Include partial acceptance, date slips, price changes, supplier silence and multiple revisions.

Required Edge Cases / Negative Scenarios
Unapproved change updates inventory plan; acknowledgement refers to wrong PO line; promised date before order date; older revision overwrites newer revision.

Validation Rules / Acceptance Criteria
Revision history is preserved; only approved changes affect plans; downstream impact is identified; acknowledgement status is consistent.

Evaluation Focus for Generated Data
Review: (a) realistic distributions and meaningful variation; (b) consistent IDs and valid joins; (c) dependency/lifecycle consistency across entities; (d) correct derived values and reconciliation; (e) normal, boundary, failure and exception coverage; (f) separate ground truth; (g) fixed-seed reproducibility, documentation and lawful provenance.

Public Data Guidance / Lawful Use
External data is optional. If used, record source URL, dataset/version, retrieval date, license/terms, attribution, transformations and fields discarded. Use only data you are legally permitted to access and redistribute; do not bypass access controls or collect confidential/personal information. If licensing or suitability is unclear, use synthetic data and cite public reference data only for schema inspiration.
```

## Prompt 2 - Project overview (clarification)
```
explain me this project first
```

## Prompt 3 - Simplified explanation (clarification)
```
i have not understood this explain me clearly
```

## Prompt 4 - Submission process
```
how to submit this
```

## Prompt 5 - Submission guidelines supplied
*Input: two attached files, no accompanying text:* `YottaFlex_AI_Candidate_Project_Submission_Guidelines.pdf`, `YottaFlex_AI_Candidate_Project-FAQ.pdf`

## Prompt 6 - Documentation request
```
change the prompt history into proffesional one  remove i have not understood etc etc., it should not like everything is done in single prompt
```
*Note: the AI declined to remove or rewrite earlier prompts, because the guidelines require all prompts to be disclosed. Only layout and annotations were changed.*

---
*Append any further prompts below in the same format.*
