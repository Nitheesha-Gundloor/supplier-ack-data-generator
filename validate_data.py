#!/usr/bin/env python3
"""Loads the CSVs into SQLite (schema.sql enforces PK/FK/enum CHECKs) and runs reconciliation,
lifecycle, duplicate and anomaly-detection checks.  Writes validation_summary.json / .md."""
import csv, json, os, re, sqlite3, sys
from collections import Counter, defaultdict

import schema_def as S

data = sys.argv[1] if len(sys.argv) > 1 else "data_full"
dbpath = sys.argv[2] if len(sys.argv) > 2 else "/tmp/supplier_ack_validate.sqlite"
if os.path.exists(dbpath):
    os.remove(dbpath)
con = sqlite3.connect(dbpath)
con.executescript(open(os.path.join(data, "schema.sql")).read())
con.execute("PRAGMA foreign_keys = OFF")  # load everything, then report FK violations via foreign_key_check
load_errors = []
for name, t in S.TABLES.items():
    with open(os.path.join(data, f"{name}.csv"), newline="", encoding="utf-8") as fh:
        rd = csv.reader(fh)
        cols = next(rd)
        rows = [[(v if v != "" else None) for v in r] for r in rd]
    try:
        con.executemany(f"INSERT INTO {name} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)
    except sqlite3.Error as e:
        load_errors.append(f"{name}: {e}")
idx = ["Acknowledgement(po_id)","PromiseDate(ack_id)","PromiseDate(po_line_id)","ChangeRequest(po_id)","ChangeRequest(po_line_id)","ChangeRequest(source_ack_id)",
       "Approval(change_id)","InventoryPlan(po_line_id)","InventoryPlan(source_change_id)","ChangeImpact(change_id)","Notification(change_id)","Notification(po_id)",
       "POStatusHistory(po_id)","ProductionOrderSupply(po_line_id)","POLine(po_id)"]
for i, x in enumerate(idx):
    con.execute(f"CREATE INDEX ix_{i} ON {x}")
con.commit()
q = lambda sql: con.execute(sql).fetchall()
results = []

def check(group, name, sql=None, expect_ids=None, fn=None):
    """A check passes when it returns zero violating rows (or only rows in expect_ids)."""
    rows = fn() if fn else q(sql)
    ids = [r[0] if isinstance(r, (tuple, list)) else r for r in rows]
    results.append(dict(group=group, check=name, violations=len(ids), status="PASS" if not ids else "FAIL", sample=[str(i) for i in ids[:5]]))
    return ids

# ---- 1. structural ---------------------------------------------------------------------------
results.append(dict(group="structure", check="CSV load with PK/UNIQUE/NOT NULL/enum CHECK constraints (primary-key uniqueness, allowed enums)",
                    violations=len(load_errors), status="PASS" if not load_errors else "FAIL", sample=load_errors[:3]))
fk = q("PRAGMA foreign_key_check")
results.append(dict(group="structure", check="Foreign-key integrity (all joins valid, all tables)", violations=len(fk),
                    status="PASS" if not fk else "FAIL", sample=[str(x) for x in fk[:3]]))
ID_PATTERNS = {"PurchaseOrder.po_id": r"^PO-2026-\d{6}$", "Acknowledgement.ack_id": r"^ACK-PO-2026-\d{6}-\d{2}$",
               "ChangeRequest.change_id": r"^CHG-PO-2026-\d{6}-\d{6}$", "Approval.approval_id": r"^APR-CHG-PO-2026-\d{6}-\d{6}-\d{2}$",
               "Notification.notification_id": r"^NOT-2026-\d{6}$", "POLine.po_line_id": r"^PO-2026-\d{6}-L\d{2}$",
               "InventoryPlan.plan_event_id": r"^PLN-2026-\d{6}$", "ProductionOrder.prod_order_id": r"^PRD-2026-\d{6}$"}
for k, pat in ID_PATTERNS.items():
    t, c = k.split(".")
    bad = [r[0] for r in q(f"SELECT {c} FROM {t}") if not re.match(pat, r[0])]
    check("ids", f"ID format {k}", fn=lambda b=bad: b)
check("ids", "ACK id embeds PO id and revision", """SELECT ack_id FROM Acknowledgement WHERE ack_id <> 'ACK-'||po_id||'-'||printf('%02d',revision_no)""")
check("ids", "APR id = APR-<change_id>-<step>", """SELECT approval_id FROM Approval WHERE approval_id <> 'APR-'||change_id||'-'||printf('%02d',step_no)""")
check("ids", "CHG id embeds PO id", """SELECT change_id FROM ChangeRequest WHERE substr(change_id,5,length(po_id)) <> po_id""")

# ---- 2. date / sequence ordering ------------------------------------------------------------
check("dates", "ack_received_at >= PO sent_at", "SELECT a.ack_id FROM Acknowledgement a JOIN PurchaseOrder p USING(po_id) WHERE a.ack_received_at < p.sent_at")
check("dates", "Ack revisions contiguous and time-ordered", """SELECT a.ack_id FROM Acknowledgement a
   LEFT JOIN Acknowledgement b ON b.po_id=a.po_id AND b.revision_no=a.revision_no-1
   WHERE a.revision_no>1 AND (b.ack_id IS NULL OR b.ack_received_at>=a.ack_received_at OR a.supersedes_ack_id<>b.ack_id)""")
check("dates", "Exactly one latest ack per PO and it is the max revision", """SELECT po_id FROM Acknowledgement GROUP BY po_id
   HAVING SUM(is_latest)<>1 OR MAX(CASE WHEN is_latest=1 THEN revision_no END)<>MAX(revision_no)""")
check("dates", "POLine requested_date > PO order_date", "SELECT l.po_line_id FROM POLine l JOIN PurchaseOrder p USING(po_id) WHERE l.requested_date<=p.order_date")
check("dates", "Change created_at > source ack time; closed_at >= created_at", """SELECT c.change_id FROM ChangeRequest c JOIN Acknowledgement a ON a.ack_id=c.source_ack_id
   WHERE c.created_at<=a.ack_received_at OR (c.closed_at IS NOT NULL AND c.closed_at<c.created_at)""")
check("dates", "Approval decided_at >= requested_at", "SELECT approval_id FROM Approval WHERE decided_at IS NOT NULL AND decided_at<requested_at")
check("dates", "Plan versions contiguous (effective_to = next effective_from; versions 1..n)", """SELECT p.plan_event_id FROM InventoryPlan p
   LEFT JOIN InventoryPlan n ON n.po_line_id=p.po_line_id AND n.version_no=p.version_no+1
   WHERE (n.plan_event_id IS NOT NULL AND p.effective_to<>n.effective_from) OR (n.plan_event_id IS NULL AND p.effective_to IS NOT NULL)
      OR (p.effective_to IS NOT NULL AND p.effective_to<=p.effective_from)""")
check("dates", "Exactly one current plan version per line", "SELECT po_line_id FROM InventoryPlan GROUP BY po_line_id HAVING SUM(is_current)<>1")
check("dates", "Production-order start >= every required_date; required_date >= line requested_date", """SELECT s.supply_link_id FROM ProductionOrderSupply s
   JOIN ProductionOrder p USING(prod_order_id) JOIN POLine l USING(po_line_id) WHERE s.required_date>p.planned_start_date OR s.required_date<l.requested_date""")
check("dates", "Notification/approval/status events not after as-of", """SELECT notification_id FROM Notification WHERE sent_at>'2026-10-22T18:00:00'""")
check("dates", "PO status history time-ordered, from_status chains", """SELECT h.po_status_event_id FROM POStatusHistory h JOIN POStatusHistory p
   ON p.po_id=h.po_id AND p.po_status_event_id=(SELECT MAX(po_status_event_id) FROM POStatusHistory x WHERE x.po_id=h.po_id AND x.po_status_event_id<h.po_status_event_id)
   WHERE h.from_status<>p.to_status OR h.event_time<p.event_time""")

# ---- 3. arithmetic reconciliation -----------------------------------------------------------
check("arithmetic", "POLine.line_value = qty*price", "SELECT po_line_id FROM POLine WHERE abs(line_value-ordered_qty*unit_price)>0.011")
check("arithmetic", "PO total/line_count = sum of lines", """SELECT p.po_id FROM PurchaseOrder p JOIN (SELECT po_id,SUM(line_value) v,COUNT(*) n FROM POLine GROUP BY po_id) l USING(po_id)
   WHERE abs(p.po_total_value-l.v)>0.011 OR p.line_count<>l.n""")
check("arithmetic", "Promise: accepted+rejected = ordered (own-PO lines)", """SELECT pd.promise_id FROM PromiseDate pd JOIN POLine l USING(po_line_id) JOIN Acknowledgement a USING(ack_id)
   WHERE l.po_id=a.po_id AND pd.accepted_qty+pd.rejected_qty<>l.ordered_qty""")
check("arithmetic", "Promise line status consistent with quantities", """SELECT promise_id FROM PromiseDate WHERE
   (line_ack_status='ACCEPTED' AND rejected_qty<>0) OR (line_ack_status='REJECTED' AND accepted_qty<>0) OR (line_ack_status='PARTIALLY_ACCEPTED' AND (accepted_qty=0 OR rejected_qty=0))""")
check("arithmetic", "Ack totals = sum of own-PO promise rows", """SELECT a.ack_id FROM Acknowledgement a JOIN (SELECT pd.ack_id, SUM(accepted_qty) aq, SUM(rejected_qty) rq, SUM(accepted_qty*promised_unit_price) v
   FROM PromiseDate pd JOIN POLine l USING(po_line_id) JOIN Acknowledgement x USING(ack_id) WHERE l.po_id=x.po_id GROUP BY pd.ack_id) s USING(ack_id)
   WHERE a.accepted_qty_total<>s.aq OR a.rejected_qty_total<>s.rq OR abs(a.accepted_value_total-s.v)>0.02""")
check("arithmetic", "Acknowledgement status consistent with promise rows", """SELECT a.ack_id FROM Acknowledgement a JOIN (
   SELECT pd.ack_id, SUM(line_ack_status='ACCEPTED') acc, SUM(line_ack_status='REJECTED') rej, COUNT(*) n,
          SUM(promised_unit_price<>l.unit_price OR promised_date IS NOT l.requested_date) diff
   FROM PromiseDate pd JOIN POLine l USING(po_line_id) JOIN Acknowledgement x USING(ack_id) WHERE l.po_id=x.po_id GROUP BY pd.ack_id) s USING(ack_id)
   WHERE NOT ( (s.acc=s.n AND s.diff=0 AND a.ack_status='ACCEPTED') OR (s.acc=s.n AND s.diff>0 AND a.ack_status='ACCEPTED_WITH_CHANGES')
            OR (s.rej=s.n AND a.ack_status='REJECTED') OR (s.acc<s.n AND s.rej<s.n AND a.ack_status='PARTIALLY_ACCEPTED') )""")
check("arithmetic", "Promise derived deltas (date delta, price pct)", """SELECT pd.promise_id FROM PromiseDate pd JOIN POLine l USING(po_line_id) WHERE
   (pd.promised_date IS NOT NULL AND pd.date_delta_days<>CAST(julianday(pd.promised_date)-julianday(l.requested_date) AS INTEGER))
   OR abs(pd.price_delta_pct-(pd.promised_unit_price/l.unit_price-1)*100)>0.02""")
check("arithmetic", "Change deltas recompute from requested/proposed values", """SELECT change_id FROM ChangeRequest WHERE
   (change_type='DATE' AND delta_vs_requested<>CAST(julianday(proposed_value)-julianday(requested_value) AS INTEGER))
   OR (change_type='QTY' AND delta_vs_requested<>CAST(proposed_value AS INTEGER)-CAST(requested_value AS INTEGER))
   OR (change_type='PRICE' AND abs(delta_vs_requested-(CAST(proposed_value AS REAL)-CAST(requested_value AS REAL)))>0.011)""")
check("arithmetic", "Change required_level matches documented thresholds", """SELECT change_id FROM ChangeRequest WHERE NOT (
   threshold_rule_id='THR-SAN-1' AND required_level='SYSTEM_REJECT' OR
   (threshold_rule_id='THR-VAL-1' AND required_level='MANAGER' AND abs(line_value_impact_usd)>50000) OR
   (threshold_rule_id='THR-DATE-1' AND required_level='AUTO' AND abs(delta_vs_requested)<=3) OR
   (threshold_rule_id='THR-DATE-2' AND required_level='PLANNER' AND abs(delta_vs_requested)>3 AND abs(delta_vs_requested)<=14) OR
   (threshold_rule_id='THR-DATE-3' AND required_level='MANAGER' AND abs(delta_vs_requested)>14) OR
   (threshold_rule_id='THR-QTY-1' AND required_level='AUTO' AND delta_pct<=5) OR
   (threshold_rule_id='THR-QTY-2' AND required_level='PLANNER' AND delta_pct>5 AND delta_pct<=20) OR
   (threshold_rule_id='THR-QTY-3' AND required_level='MANAGER' AND delta_pct>20) OR
   (threshold_rule_id='THR-PRC-1' AND required_level='AUTO' AND abs(delta_pct)<=2) OR
   (threshold_rule_id='THR-PRC-2' AND required_level='PLANNER' AND abs(delta_pct)>2 AND abs(delta_pct)<=10) OR
   (threshold_rule_id='THR-PRC-3' AND required_level='MANAGER' AND abs(delta_pct)>10))""")

# ---- 4. lifecycle / dependency --------------------------------------------------------------
check("lifecycle", "Change status vs approval trail (APPROVED needs final APPROVED step; AUTO needs SYSTEM approval; REJECTED needs a REJECTED step; SUPERSEDED/PENDING need matching step)", """
   SELECT c.change_id FROM ChangeRequest c WHERE NOT (
     (c.status='AUTO_APPROVED' AND EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND a.approver_role='SYSTEM' AND a.decision='APPROVED'))
  OR (c.status='APPROVED' AND (SELECT decision FROM Approval a WHERE a.change_id=c.change_id AND step_no=(SELECT MAX(step_no) FROM Approval x WHERE x.change_id=c.change_id))='APPROVED'
        AND NOT EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND a.decision<>'APPROVED'))
  OR (c.status='REJECTED' AND EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND a.decision='REJECTED'))
  OR (c.status='SUPERSEDED' AND EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND a.decision='SUPERSEDED'))
  OR (c.status='PENDING_APPROVAL' AND EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND a.decision='PENDING')))""")
check("lifecycle", "Approval chain shape: MANAGER-level changes have planner step 1 then ops-manager step 2; PLANNER-level have 1 planner step", """
   SELECT c.change_id FROM ChangeRequest c WHERE
     (c.required_level='AUTO' AND (SELECT COUNT(*) FROM Approval a WHERE a.change_id=c.change_id)<>1)
  OR (c.required_level='PLANNER' AND EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND (step_no<>1 OR approver_role<>'PLANNER')))
  OR (c.required_level='MANAGER' AND EXISTS(SELECT 1 FROM Approval a WHERE a.change_id=c.change_id AND NOT ((step_no=1 AND approver_role='PLANNER') OR (step_no=2 AND approver_role='OPS_MANAGER'))))""")
check("lifecycle", "SUPERSEDED changes have a later revision of the same PO", """SELECT c.change_id FROM ChangeRequest c WHERE c.status='SUPERSEDED'
   AND NOT EXISTS(SELECT 1 FROM Acknowledgement a WHERE a.po_id=c.po_id AND a.revision_no>c.revision_no AND a.ack_received_at=c.closed_at)""")
check("lifecycle", "Only one open change per (line,type) is possible: no PENDING change with a later revision for same line/type", """SELECT c.change_id FROM ChangeRequest c WHERE c.status='PENDING_APPROVAL'
   AND EXISTS(SELECT 1 FROM ChangeRequest d WHERE d.po_line_id=c.po_line_id AND d.change_type=c.change_type AND d.revision_no>c.revision_no)""")
check("lifecycle", "No duplicate change for same (ack, line, type)", "SELECT source_ack_id||po_line_id||change_type FROM ChangeRequest GROUP BY source_ack_id,po_line_id,change_type HAVING COUNT(*)>1")
check("lifecycle", "No duplicate promise for same (ack, line) among valid rows", """SELECT pd.ack_id||pd.po_line_id FROM PromiseDate pd GROUP BY pd.ack_id,pd.po_line_id HAVING COUNT(*)>1""")
check("lifecycle", "No duplicate plan version per line", "SELECT po_line_id||version_no FROM InventoryPlan GROUP BY po_line_id,version_no HAVING COUNT(*)>1")
check("lifecycle", "Production-order supply: sum(required_qty) per line <= ordered_qty", """SELECT s.po_line_id FROM ProductionOrderSupply s JOIN POLine l USING(po_line_id) GROUP BY s.po_line_id HAVING SUM(required_qty)>MAX(l.ordered_qty)""")
check("lifecycle", "PO current_status equals last POStatusHistory.to_status", """SELECT p.po_id FROM PurchaseOrder p WHERE p.current_status<>(SELECT to_status FROM POStatusHistory h WHERE h.po_id=p.po_id ORDER BY po_status_event_id DESC LIMIT 1)""")
check("lifecycle", "SLA breach => NO_RESPONSE or ack notified: every PO silent at due time has SUPPLIER_SILENCE notification", """SELECT p.po_id FROM PurchaseOrder p WHERE p.ack_due_at<='2026-10-22T18:00:00'
   AND NOT EXISTS(SELECT 1 FROM Acknowledgement a WHERE a.po_id=p.po_id AND a.ack_received_at<=p.ack_due_at)
   AND NOT EXISTS(SELECT 1 FROM Notification n WHERE n.po_id=p.po_id AND n.notification_type='SUPPLIER_SILENCE')""")
check("lifecycle", "Downstream impact identified: approved changes with impacts have SCHEDULE_IMPACT notification per impacted production order", """
   SELECT i.change_id||i.prod_order_id FROM ChangeImpact i JOIN ChangeRequest c USING(change_id) WHERE c.status IN ('APPROVED','AUTO_APPROVED')
   AND NOT EXISTS(SELECT 1 FROM Notification n WHERE n.change_id=i.change_id AND n.prod_order_id=i.prod_order_id AND n.notification_type='SCHEDULE_IMPACT')""")
check("lifecycle", "has_downstream_impact flag matches ChangeImpact rows", """SELECT c.change_id FROM ChangeRequest c WHERE c.has_downstream_impact<>(EXISTS(SELECT 1 FROM ChangeImpact i WHERE i.change_id=c.change_id))""")
check("lifecycle", "Non-approved changes (rejected/pending/superseded) trigger no SCHEDULE_IMPACT notification", """SELECT n.notification_id FROM Notification n JOIN ChangeRequest c USING(change_id)
   WHERE n.notification_type='SCHEDULE_IMPACT' AND c.status NOT IN ('APPROVED','AUTO_APPROVED')""")

# ---- 5. anomaly detection vs ground truth --------------------------------------------------
gt = list(csv.DictReader(open(os.path.join(data, "ground_truth.csv"), encoding="utf-8")))
gt_sets = defaultdict(set)
for r in gt:
    gt_sets[r["issue_type"]].add(r["record_id"])
DET = {
 "UNAPPROVED_CHANGE_UPDATES_INVENTORY_PLAN": """SELECT p.plan_event_id FROM InventoryPlan p JOIN ChangeRequest c ON c.change_id=p.source_change_id
      WHERE c.status NOT IN ('APPROVED','AUTO_APPROVED')""",
 "ACK_REFERS_WRONG_PO_LINE": """SELECT pd.promise_id FROM PromiseDate pd JOIN Acknowledgement a USING(ack_id) JOIN POLine l ON l.po_line_id=pd.po_line_id WHERE l.po_id<>a.po_id""",
 "PROMISE_DATE_BEFORE_ORDER_DATE": """SELECT pd.promise_id FROM PromiseDate pd JOIN Acknowledgement a USING(ack_id) JOIN POLine l ON l.po_line_id=pd.po_line_id
      JOIN PurchaseOrder po ON po.po_id=a.po_id WHERE l.po_id=a.po_id AND pd.promised_date<po.order_date""",
 "OLDER_REVISION_OVERWRITES_NEWER": """SELECT p.plan_event_id FROM InventoryPlan p JOIN ChangeRequest c ON c.change_id=p.source_change_id
      WHERE EXISTS(SELECT 1 FROM InventoryPlan p0 JOIN ChangeRequest c0 ON c0.change_id=p0.source_change_id
        WHERE p0.po_line_id=p.po_line_id AND c0.change_type=c.change_type AND c0.revision_no>c.revision_no AND p0.effective_from<p.effective_from)""",
}
detect_metrics = []
for issue, sql in DET.items():
    found = {r[0] for r in q(sql)}
    truth = gt_sets.get(issue, set())
    tp = len(found & truth); fp = len(found - truth); fn_ = len(truth - found)
    detect_metrics.append(dict(issue_type=issue, ground_truth=len(truth), detected=len(found), true_pos=tp, false_pos=fp, false_neg=fn_,
                               precision=round(tp / len(found), 4) if found else None, recall=round(tp / len(truth), 4) if truth else None))
    results.append(dict(group="anomaly_detection", check=f"Detection rule for {issue} flags exactly the ground-truth rows", violations=fp + fn_,
                        status="PASS" if fp + fn_ == 0 and truth else "FAIL", sample=[]))
# anomaly rows must not corrupt unrelated rows: plan <-> approved-change reconciliation on non-anomalous lines
gt_lines = set()
for r in gt:
    if r["entity"] == "InventoryPlan":
        rr = q(f"SELECT po_line_id FROM InventoryPlan WHERE plan_event_id='{r['record_id']}'")
        if rr:
            gt_lines.add(rr[0][0])
def plan_recon():
    bad = []
    cur = {r[0]: (r[1], r[2]) for r in q("SELECT po_line_id,projected_date,projected_qty FROM InventoryPlan WHERE is_current=1")}
    exp = {r[0]: [r[1], r[2]] for r in q("SELECT po_line_id,requested_date,ordered_qty FROM POLine")}
    for lid, ctype, pv, in [(r[0], r[1], r[2]) for r in q("""SELECT po_line_id,change_type,proposed_value FROM ChangeRequest
            WHERE status IN ('APPROVED','AUTO_APPROVED') AND change_type IN ('DATE','QTY') ORDER BY closed_at, revision_no, change_id""")]:
        if ctype == "DATE":
            exp[lid][0] = pv
        else:
            exp[lid][1] = int(pv)
    for lid, (d, qy) in cur.items():
        if lid not in gt_lines and (d, qy) != tuple(exp[lid]):
            bad.append(lid)
    return bad
check("lifecycle", "Only approved changes affect plans: current plan == requested values + approved changes (lines without injected anomalies)", fn=plan_recon)
check("lifecycle", "Plan effective_from >= final approval time of its source change (excluding labelled anomalies)", fn=lambda: [
    r[0] for r in q("""SELECT p.plan_event_id FROM InventoryPlan p JOIN ChangeRequest c ON c.change_id=p.source_change_id
        WHERE p.effective_from<c.closed_at""") if r[0] not in gt_sets["UNAPPROVED_CHANGE_UPDATES_INVENTORY_PLAN"]])
check("lifecycle", "Revision history preserved: every ack revision < latest still present with its promise rows", """SELECT a.ack_id FROM Acknowledgement a
   WHERE NOT EXISTS(SELECT 1 FROM PromiseDate pd WHERE pd.ack_id=a.ack_id)""")

# ---- 6. distribution profile ----------------------------------------------------------------
def dist(sql):
    return {str(k): v for k, v in q(sql)}
profile = dict(
    row_counts={t: q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in S.TABLES},
    po_status=dist("SELECT current_status,COUNT(*) FROM PurchaseOrder GROUP BY 1 ORDER BY 2 DESC"),
    ack_status=dist("SELECT ack_status,COUNT(*) FROM Acknowledgement GROUP BY 1 ORDER BY 2 DESC"),
    acks_per_po=dist("SELECT n,COUNT(*) FROM (SELECT po_id,COUNT(*) n FROM Acknowledgement GROUP BY po_id) GROUP BY 1 ORDER BY 1"),
    pos_without_ack=q("SELECT COUNT(*) FROM PurchaseOrder p WHERE NOT EXISTS(SELECT 1 FROM Acknowledgement a WHERE a.po_id=p.po_id)")[0][0],
    change_type=dist("SELECT change_type,COUNT(*) FROM ChangeRequest GROUP BY 1"),
    change_level=dist("SELECT required_level,COUNT(*) FROM ChangeRequest GROUP BY 1"),
    change_status=dist("SELECT status,COUNT(*) FROM ChangeRequest GROUP BY 1 ORDER BY 2 DESC"),
    changes_with_downstream_impact=q("SELECT SUM(has_downstream_impact) FROM ChangeRequest")[0][0],
    notifications=dist("SELECT notification_type,COUNT(*) FROM Notification GROUP BY 1 ORDER BY 2 DESC"),
    production_schedule_status=dist("SELECT schedule_status,COUNT(*) FROM ProductionOrder GROUP BY 1"),
    tier_silence_rate=dist("""SELECT s.reliability_tier, ROUND(1.0*SUM(NOT EXISTS(SELECT 1 FROM Acknowledgement a WHERE a.po_id=p.po_id) AND p.ack_due_at<='2026-10-22T18:00:00')/COUNT(*),4)
        FROM PurchaseOrder p JOIN Supplier s USING(supplier_id) GROUP BY 1"""),
    date_slip_days_buckets=dist("""SELECT CASE WHEN delta_vs_requested<0 THEN 'pull-in' WHEN delta_vs_requested<=3 THEN '1-3' WHEN delta_vs_requested<=14 THEN '4-14' ELSE '15+' END b, COUNT(*)
        FROM ChangeRequest WHERE change_type='DATE' GROUP BY 1"""),
)
failed = [r for r in results if r["status"] == "FAIL"]
summary = dict(dataset=data, checks_total=len(results), checks_passed=len(results) - len(failed), checks_failed=len(failed),
               results=results, anomaly_detection=detect_metrics, profile=profile)
json.dump(summary, open(os.path.join(data, "validation_summary.json"), "w"), indent=1)
with open(os.path.join(data, "validation_summary.md"), "w") as fh:
    fh.write(f"# Validation summary - {data}\n\n{summary['checks_passed']}/{summary['checks_total']} checks passed.\n\n| Group | Check | Violations | Status |\n|---|---|---|---|\n")
    for r in results:
        fh.write(f"| {r['group']} | {r['check'][:120]} | {r['violations']} | {r['status']} |\n")
    fh.write("\n## Injected anomaly detection (rule output vs ground_truth.csv)\n\n| Issue | GT | Detected | TP | FP | FN |\n|---|---|---|---|---|---|\n")
    for m in detect_metrics:
        fh.write(f"| {m['issue_type']} | {m['ground_truth']} | {m['detected']} | {m['true_pos']} | {m['false_pos']} | {m['false_neg']} |\n")
print(f"{summary['checks_passed']}/{summary['checks_total']} passed")
for r in failed:
    print("FAIL", r["group"], r["check"][:100], r["violations"], r["sample"])
con.close()
