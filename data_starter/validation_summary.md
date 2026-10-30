# Validation summary - data_starter

53/53 checks passed.

| Group | Check | Violations | Status |
|---|---|---|---|
| structure | CSV load with PK/UNIQUE/NOT NULL/enum CHECK constraints (primary-key uniqueness, allowed enums) | 0 | PASS |
| structure | Foreign-key integrity (all joins valid, all tables) | 0 | PASS |
| ids | ID format PurchaseOrder.po_id | 0 | PASS |
| ids | ID format Acknowledgement.ack_id | 0 | PASS |
| ids | ID format ChangeRequest.change_id | 0 | PASS |
| ids | ID format Approval.approval_id | 0 | PASS |
| ids | ID format Notification.notification_id | 0 | PASS |
| ids | ID format POLine.po_line_id | 0 | PASS |
| ids | ID format InventoryPlan.plan_event_id | 0 | PASS |
| ids | ID format ProductionOrder.prod_order_id | 0 | PASS |
| ids | ACK id embeds PO id and revision | 0 | PASS |
| ids | APR id = APR-<change_id>-<step> | 0 | PASS |
| ids | CHG id embeds PO id | 0 | PASS |
| dates | ack_received_at >= PO sent_at | 0 | PASS |
| dates | Ack revisions contiguous and time-ordered | 0 | PASS |
| dates | Exactly one latest ack per PO and it is the max revision | 0 | PASS |
| dates | POLine requested_date > PO order_date | 0 | PASS |
| dates | Change created_at > source ack time; closed_at >= created_at | 0 | PASS |
| dates | Approval decided_at >= requested_at | 0 | PASS |
| dates | Plan versions contiguous (effective_to = next effective_from; versions 1..n) | 0 | PASS |
| dates | Exactly one current plan version per line | 0 | PASS |
| dates | Production-order start >= every required_date; required_date >= line requested_date | 0 | PASS |
| dates | Notification/approval/status events not after as-of | 0 | PASS |
| dates | PO status history time-ordered, from_status chains | 0 | PASS |
| arithmetic | POLine.line_value = qty*price | 0 | PASS |
| arithmetic | PO total/line_count = sum of lines | 0 | PASS |
| arithmetic | Promise: accepted+rejected = ordered (own-PO lines) | 0 | PASS |
| arithmetic | Promise line status consistent with quantities | 0 | PASS |
| arithmetic | Ack totals = sum of own-PO promise rows | 0 | PASS |
| arithmetic | Acknowledgement status consistent with promise rows | 0 | PASS |
| arithmetic | Promise derived deltas (date delta, price pct) | 0 | PASS |
| arithmetic | Change deltas recompute from requested/proposed values | 0 | PASS |
| arithmetic | Change required_level matches documented thresholds | 0 | PASS |
| lifecycle | Change status vs approval trail (APPROVED needs final APPROVED step; AUTO needs SYSTEM approval; REJECTED needs a REJECT | 0 | PASS |
| lifecycle | Approval chain shape: MANAGER-level changes have planner step 1 then ops-manager step 2; PLANNER-level have 1 planner st | 0 | PASS |
| lifecycle | SUPERSEDED changes have a later revision of the same PO | 0 | PASS |
| lifecycle | Only one open change per (line,type) is possible: no PENDING change with a later revision for same line/type | 0 | PASS |
| lifecycle | No duplicate change for same (ack, line, type) | 0 | PASS |
| lifecycle | No duplicate promise for same (ack, line) among valid rows | 0 | PASS |
| lifecycle | No duplicate plan version per line | 0 | PASS |
| lifecycle | Production-order supply: sum(required_qty) per line <= ordered_qty | 0 | PASS |
| lifecycle | PO current_status equals last POStatusHistory.to_status | 0 | PASS |
| lifecycle | SLA breach => NO_RESPONSE or ack notified: every PO silent at due time has SUPPLIER_SILENCE notification | 0 | PASS |
| lifecycle | Downstream impact identified: approved changes with impacts have SCHEDULE_IMPACT notification per impacted production or | 0 | PASS |
| lifecycle | has_downstream_impact flag matches ChangeImpact rows | 0 | PASS |
| lifecycle | Non-approved changes (rejected/pending/superseded) trigger no SCHEDULE_IMPACT notification | 0 | PASS |
| anomaly_detection | Detection rule for UNAPPROVED_CHANGE_UPDATES_INVENTORY_PLAN flags exactly the ground-truth rows | 0 | PASS |
| anomaly_detection | Detection rule for ACK_REFERS_WRONG_PO_LINE flags exactly the ground-truth rows | 0 | PASS |
| anomaly_detection | Detection rule for PROMISE_DATE_BEFORE_ORDER_DATE flags exactly the ground-truth rows | 0 | PASS |
| anomaly_detection | Detection rule for OLDER_REVISION_OVERWRITES_NEWER flags exactly the ground-truth rows | 0 | PASS |
| lifecycle | Only approved changes affect plans: current plan == requested values + approved changes (lines without injected anomalie | 0 | PASS |
| lifecycle | Plan effective_from >= final approval time of its source change (excluding labelled anomalies) | 0 | PASS |
| lifecycle | Revision history preserved: every ack revision < latest still present with its promise rows | 0 | PASS |

## Injected anomaly detection (rule output vs ground_truth.csv)

| Issue | GT | Detected | TP | FP | FN |
|---|---|---|---|---|---|
| UNAPPROVED_CHANGE_UPDATES_INVENTORY_PLAN | 2 | 2 | 2 | 0 | 0 |
| ACK_REFERS_WRONG_PO_LINE | 2 | 2 | 2 | 0 | 0 |
| PROMISE_DATE_BEFORE_ORDER_DATE | 2 | 2 | 2 | 0 | 0 |
| OLDER_REVISION_OVERWRITES_NEWER | 2 | 2 | 2 | 0 | 0 |
