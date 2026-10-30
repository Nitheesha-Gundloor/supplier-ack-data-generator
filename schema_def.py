"""Single source of truth for the data dictionary, DDL and CSV column order."""

def f(name, type_, req, allowed="", unit="", uniq="", rule="", fk=""):
    return dict(field=name, type=type_, required=req, allowed=allowed, unit=unit,
                uniqueness=uniq, rule=rule, fk=fk)

TABLES = {}   # ordered by dependency (parents first)

def T(name, desc, cardinality, fields):
    TABLES[name] = dict(desc=desc, cardinality=cardinality, fields=fields)

T("ApprovalThreshold", "Reference table of approval-threshold rules (documented business logic).",
  "Referenced 1:N by ChangeRequest.threshold_rule_id", [
    f("rule_id", "string", "Y", uniq="PK", rule="Pattern THR-<DATE|QTY|PRC|VAL|SAN>-<n>"),
    f("change_type", "string", "Y", "DATE,QTY,PRICE,ANY", rule="Change type the rule evaluates"),
    f("required_level", "string", "Y", "AUTO,PLANNER,MANAGER,SYSTEM_REJECT", rule="Approval level mandated"),
    f("metric", "string", "Y", rule="abs_days | shortfall_pct | abs_price_pct | abs_line_value_usd | date_vs_order_date"),
    f("lower_exclusive", "decimal4", "N", unit="per metric", rule="Band lower bound (exclusive); null = none"),
    f("upper_inclusive", "decimal4", "N", unit="per metric", rule="Band upper bound (inclusive); null = unbounded"),
    f("unit", "string", "Y", "days,percent,USD"),
    f("description", "string", "Y"),
])
T("AppUser", "Internal users who receive notifications or approve changes.",
  "1:N to PurchaseOrder (planner), Approval, Notification; 1:1 optional to Warehouse (operator)", [
    f("user_id", "string", "Y", uniq="PK", rule="USR-NNN"),
    f("full_name", "string", "Y", rule="Synthetic name"),
    f("role", "string", "Y", "PLANNER,OPS_MANAGER,LOGISTICS_ANALYST,WAREHOUSE_OPERATOR"),
    f("active", "bool", "Y", "0,1", rule="1 = active"),
])
T("Warehouse", "Receiving warehouse / plant.", "1:N to PurchaseOrder, InventoryPlan, ProductionOrder", [
    f("warehouse_id", "string", "Y", uniq="PK", rule="WH-NN"),
    f("warehouse_name", "string", "Y"),
    f("region", "string", "Y"),
    f("operator_user_id", "string", "Y", rule="Warehouse operator receiving inbound notices", fk="AppUser.user_id"),
])
T("Supplier", "Supplier master.", "1:N to PurchaseOrder", [
    f("supplier_id", "string", "Y", uniq="PK", rule="SUP-NNNN"),
    f("supplier_name", "string", "Y"),
    f("country", "string", "Y"),
    f("reliability_tier", "string", "Y", "A,B,C", rule="Drives behaviour probabilities (A best)"),
    f("ack_sla_days", "int", "Y", unit="days", rule="1..7; acknowledgement due = sent_at + SLA"),
    f("payment_terms_days", "int", "Y", "30,45,60", unit="days"),
    f("status", "string", "Y", "ACTIVE,ON_HOLD"),
    f("effective_from", "date", "Y", rule="<= first PO date"),
])
T("Item", "Item master (components and finished goods).", "1:N to POLine, ProductionOrder, InventoryPlan", [
    f("item_id", "string", "Y", uniq="PK", rule="ITM-NNNN"),
    f("description", "string", "Y"),
    f("category", "string", "Y", "RAW,COMPONENT,PACKAGING,FG", rule="FG used only on ProductionOrder"),
    f("uom", "string", "Y", "EA,KG,L"),
    f("pack_size", "int", "Y", unit="uom", rule=">=1"),
    f("standard_cost", "decimal2", "Y", unit="USD per uom", rule=">0"),
    f("planning_lead_time_days", "int", "Y", unit="days", rule="10..55"),
])
T("PurchaseOrder", "PO header. Requested values are immutable; current_status is a snapshot as of 2026-10-22 and every transition is stored in POStatusHistory.",
  "Supplier 1:N PO; PO 1:N POLine; PO 1:N Acknowledgement", [
    f("po_id", "string", "Y", uniq="PK", rule="PO-2026-NNNNNN, zero padded, chronological"),
    f("supplier_id", "string", "Y", fk="Supplier.supplier_id"),
    f("warehouse_id", "string", "Y", fk="Warehouse.warehouse_id"),
    f("planner_id", "string", "Y", fk="AppUser.user_id", rule="user.role = PLANNER"),
    f("order_date", "date", "Y", rule="Weekday, 2026-01-02..2026-10-20"),
    f("sent_at", "datetime", "Y", rule="Same calendar day as order_date"),
    f("ack_due_at", "datetime", "Y", rule="sent_at + supplier.ack_sla_days"),
    f("currency", "string", "Y", "USD"),
    f("line_count", "int", "Y", rule="= count(POLine) (derived)"),
    f("po_total_value", "decimal2", "Y", unit="USD", rule="= sum(POLine.line_value) (derived)"),
    f("current_status", "string", "Y",
      "SENT,NO_RESPONSE,CHANGE_PENDING_APPROVAL,SUPPLIER_REJECTED,PARTIALLY_CONFIRMED,CONFIRMED_WITH_CHANGES,CONFIRMED",
      rule="Derived from latest ack + open changes; equals last POStatusHistory.to_status"),
])
T("POLine", "PO line with the originally requested qty/price/date (never overwritten).",
  "PO 1:N POLine; POLine N:M Acknowledgement via PromiseDate; POLine N:M ProductionOrder via ProductionOrderSupply", [
    f("po_line_id", "string", "Y", uniq="PK", rule="<po_id>-Lnn"),
    f("po_id", "string", "Y", fk="PurchaseOrder.po_id"),
    f("line_no", "int", "Y", rule="1..5, unique within PO"),
    f("item_id", "string", "Y", fk="Item.item_id", rule="category <> FG"),
    f("ordered_qty", "int", "Y", unit="uom", rule=">0"),
    f("uom", "string", "Y", "EA,KG,L"),
    f("unit_price", "decimal2", "Y", unit="USD per uom", rule=">0"),
    f("requested_date", "date", "Y", rule="> PO order_date"),
    f("line_value", "decimal2", "Y", unit="USD", rule="= ordered_qty * unit_price (derived)"),
    f("line_status_current", "string", "Y", "UNCONFIRMED,CONFIRMED,PARTIALLY_CONFIRMED,REJECTED,CHANGE_PENDING",
      rule="Snapshot derived from latest promise + open changes"),
])
T("Acknowledgement", "Supplier acknowledgement revision for a PO. Revisions are new rows; older rows are never overwritten.",
  "PO 1:N Acknowledgement; Acknowledgement 1:N PromiseDate; self-link supersedes_ack_id (optional)", [
    f("ack_id", "string", "Y", uniq="PK", rule="ACK-<po_id>-NN (NN = revision_no)"),
    f("po_id", "string", "Y", fk="PurchaseOrder.po_id"),
    f("revision_no", "int", "Y", rule="1..n, contiguous per PO; time-ordered"),
    f("ack_received_at", "datetime", "Y", rule=">= PO.sent_at and <= 2026-10-22T18:00:00"),
    f("channel", "string", "Y", "EDI,PORTAL,EMAIL"),
    f("ack_status", "string", "Y", "ACCEPTED,ACCEPTED_WITH_CHANGES,PARTIALLY_ACCEPTED,REJECTED",
      rule="Derived from the PO's own PromiseDate rows"),
    f("supersedes_ack_id", "string", "N", fk="Acknowledgement.ack_id", rule="Null for revision 1"),
    f("is_latest", "bool", "Y", "0,1", rule="Exactly one latest ack per PO"),
    f("accepted_qty_total", "int", "Y", unit="uom (mixed)", rule="= sum(accepted_qty) of the PO's own promise rows"),
    f("rejected_qty_total", "int", "Y", unit="uom (mixed)", rule="= sum(rejected_qty) of the PO's own promise rows"),
    f("accepted_value_total", "decimal2", "Y", unit="USD", rule="= sum(accepted_qty*promised_unit_price)"),
])
T("PromiseDate", "Line-level promise inside an acknowledgement revision; bridge resolving Acknowledgement N:M POLine.",
  "Acknowledgement 1:N PromiseDate; POLine 1:N PromiseDate", [
    f("promise_id", "string", "Y", uniq="PK", rule="PRM-<ack_id>-Lnn (injected anomaly rows: -Xnn)"),
    f("ack_id", "string", "Y", fk="Acknowledgement.ack_id"),
    f("po_line_id", "string", "Y", fk="POLine.po_line_id", rule="Must belong to the acknowledgement's PO"),
    f("accepted_qty", "int", "Y", unit="uom", rule=">=0"),
    f("rejected_qty", "int", "Y", unit="uom", rule="accepted_qty + rejected_qty = ordered_qty"),
    f("line_ack_status", "string", "Y", "ACCEPTED,PARTIALLY_ACCEPTED,REJECTED", rule="Derived from accepted vs ordered qty"),
    f("promised_date", "date", "N", rule="Null when accepted_qty = 0; should be >= PO order_date"),
    f("promised_unit_price", "decimal2", "Y", unit="USD per uom", rule=">0"),
    f("reason_code", "string", "N", "CAPACITY,MATERIAL_SHORTAGE,QUALITY_HOLD,DISCONTINUED,LOGISTICS,PRICE_ADJUSTMENT",
      rule="Required when line is partial/rejected"),
    f("date_delta_days", "int", "N", unit="days", rule="= promised_date - requested_date (derived)"),
    f("price_delta_pct", "decimal4", "Y", unit="percent", rule="= (promised/unit_price - 1)*100 (derived)"),
])
T("ChangeRequest", "Difference between a supplier proposal and the previously proposed value, evaluated against the REQUESTED value for thresholds.",
  "Acknowledgement 1:N ChangeRequest; POLine 1:N ChangeRequest; ChangeRequest 1:N Approval", [
    f("change_id", "string", "Y", uniq="PK", rule="CHG-<po_id>-NNNNNN (counter per PO)"),
    f("po_id", "string", "Y", fk="PurchaseOrder.po_id"),
    f("po_line_id", "string", "Y", fk="POLine.po_line_id"),
    f("source_ack_id", "string", "Y", fk="Acknowledgement.ack_id"),
    f("revision_no", "int", "Y", rule="= source acknowledgement revision"),
    f("change_type", "string", "Y", "DATE,QTY,PRICE"),
    f("requested_value", "string", "Y", rule="Original PO-line value (ISO date / integer / 2-dp price)"),
    f("proposed_value", "string", "Y", rule="Supplier proposed value, same format"),
    f("delta_vs_requested", "decimal2", "Y", unit="days | units | USD per uom", rule="proposed - requested (derived)"),
    f("delta_pct", "decimal4", "N", unit="percent", rule="QTY: shortfall % (positive = short); PRICE: signed %; DATE: null"),
    f("line_value_impact_usd", "decimal2", "Y", unit="USD", rule="DATE: 0; QTY: delta*unit_price; PRICE: delta*accepted_qty"),
    f("threshold_rule_id", "string", "Y", fk="ApprovalThreshold.rule_id", rule="Rule that set required_level"),
    f("required_level", "string", "Y", "AUTO,PLANNER,MANAGER,SYSTEM_REJECT"),
    f("status", "string", "Y", "PENDING_APPROVAL,APPROVED,AUTO_APPROVED,REJECTED,SUPERSEDED"),
    f("created_at", "datetime", "Y", rule="source ack time + 60 s"),
    f("closed_at", "datetime", "N", rule=">= created_at; null while PENDING_APPROVAL"),
    f("has_downstream_impact", "bool", "Y", "0,1", rule="1 if any ChangeImpact row exists"),
])
T("Approval", "Approval steps/events per change (system auto-approval, planner, ops manager).",
  "ChangeRequest 1:N Approval (max 2 steps)", [
    f("approval_id", "string", "Y", uniq="PK", rule="APR-<change_id>-NN (NN = step_no)"),
    f("change_id", "string", "Y", fk="ChangeRequest.change_id"),
    f("step_no", "int", "Y", "1,2"),
    f("approver_role", "string", "Y", "SYSTEM,PLANNER,OPS_MANAGER"),
    f("approver_user_id", "string", "N", fk="AppUser.user_id", rule="Null for SYSTEM"),
    f("decision", "string", "Y", "APPROVED,REJECTED,PENDING,SUPERSEDED"),
    f("requested_at", "datetime", "Y"),
    f("decided_at", "datetime", "N", rule=">= requested_at; null while PENDING"),
    f("reason_code", "string", "Y",
      "WITHIN_TOLERANCE,DOWNSTREAM_IMPACT_ACCEPTED,DOWNSTREAM_IMPACT_UNACCEPTABLE,PRICE_NOT_JUSTIFIED,INVALID_DATE,NEWER_REVISION_RECEIVED,PENDING_REVIEW"),
])
T("InventoryPlan", "Projected-supply plan versions per PO line (append-only; one row per version).",
  "POLine 1:N InventoryPlan; ChangeRequest 1:N InventoryPlan (optional)", [
    f("plan_event_id", "string", "Y", uniq="PK", rule="PLN-2026-NNNNNN in effective_from order"),
    f("po_line_id", "string", "Y", fk="POLine.po_line_id"),
    f("item_id", "string", "Y", fk="Item.item_id"),
    f("warehouse_id", "string", "Y", fk="Warehouse.warehouse_id"),
    f("version_no", "int", "Y", rule="1..n contiguous per line"),
    f("event_type", "string", "Y", "INITIAL,CHANGE_APPLIED"),
    f("source_change_id", "string", "N", fk="ChangeRequest.change_id", rule="Null for INITIAL; must be an approved change"),
    f("projected_qty", "int", "Y", unit="uom"),
    f("projected_date", "date", "Y"),
    f("effective_from", "datetime", "Y", rule=">= final approval time of source change"),
    f("effective_to", "datetime", "N", rule="= next version effective_from; null for current"),
    f("is_current", "bool", "Y", "0,1", rule="Exactly one per line"),
])
T("ProductionOrder", "Downstream production order consuming PO-line supply.",
  "ProductionOrder N:M POLine via ProductionOrderSupply", [
    f("prod_order_id", "string", "Y", uniq="PK", rule="PRD-2026-NNNNNN"),
    f("warehouse_id", "string", "Y", fk="Warehouse.warehouse_id", rule="Plant"),
    f("owner_planner_id", "string", "Y", fk="AppUser.user_id"),
    f("finished_item_id", "string", "Y", fk="Item.item_id", rule="category = FG"),
    f("planned_start_date", "date", "Y", rule=">= every linked required_date"),
    f("planned_qty", "int", "Y", unit="EA"),
    f("priority", "string", "Y", "HIGH,NORMAL,LOW"),
    f("schedule_status", "string", "Y", "ON_TRACK,AT_RISK,RELEASED,DELAYED",
      rule="Derived from baseline (approved-only) plan vs required date/qty and as-of date"),
])
T("ProductionOrderSupply", "Bridge: material requirement of a production order against a PO line.",
  "ProductionOrder N:M POLine", [
    f("supply_link_id", "string", "Y", uniq="PK", rule="PSL-NNNNNN"),
    f("prod_order_id", "string", "Y", fk="ProductionOrder.prod_order_id"),
    f("po_line_id", "string", "Y", fk="POLine.po_line_id"),
    f("required_qty", "int", "Y", unit="uom", rule="sum per line <= ordered_qty"),
    f("required_date", "date", "Y", rule=">= POLine.requested_date"),
])
T("ChangeImpact", "Identified downstream impact of a change on a production order (evaluated at change creation).",
  "ChangeRequest N:M ProductionOrder", [
    f("impact_id", "string", "Y", uniq="PK", rule="IMP-NNNNNN"),
    f("change_id", "string", "Y", fk="ChangeRequest.change_id"),
    f("prod_order_id", "string", "Y", fk="ProductionOrder.prod_order_id"),
    f("supply_link_id", "string", "Y", fk="ProductionOrderSupply.supply_link_id"),
    f("impact_type", "string", "Y", "LATE_SUPPLY,SHORT_SUPPLY"),
    f("days_late", "int", "N", unit="days", rule="LATE_SUPPLY only; >0"),
    f("shortage_qty", "int", "N", unit="uom", rule="SHORT_SUPPLY only; >0"),
    f("evaluated_at", "datetime", "Y", rule="= change.created_at"),
])
T("Notification", "Notifications to planners, managers, logistics analysts and warehouse operators.",
  "AppUser 1:N Notification; ChangeRequest 1:N Notification (optional)", [
    f("notification_id", "string", "Y", uniq="PK", rule="NOT-2026-NNNNNN in sent_at order"),
    f("notification_type", "string", "Y",
      "APPROVAL_REQUIRED,CHANGE_REJECTED,SCHEDULE_IMPACT,INBOUND_RESCHEDULE,SUPPLIER_SILENCE"),
    f("recipient_user_id", "string", "Y", fk="AppUser.user_id"),
    f("po_id", "string", "Y", fk="PurchaseOrder.po_id"),
    f("change_id", "string", "N", fk="ChangeRequest.change_id"),
    f("prod_order_id", "string", "N", fk="ProductionOrder.prod_order_id"),
    f("severity", "string", "Y", "INFO,WARNING,CRITICAL"),
    f("sent_at", "datetime", "Y", rule="<= 2026-10-22T18:00:00"),
    f("message", "string", "Y"),
])
T("POStatusHistory", "Append-only PO lifecycle transitions.", "PO 1:N POStatusHistory", [
    f("po_status_event_id", "string", "Y", uniq="PK", rule="PSE-NNNNNN"),
    f("po_id", "string", "Y", fk="PurchaseOrder.po_id"),
    f("from_status", "string", "N", rule="Null for first event"),
    f("to_status", "string", "Y",
      "SENT,NO_RESPONSE,CHANGE_PENDING_APPROVAL,SUPPLIER_REJECTED,PARTIALLY_CONFIRMED,CONFIRMED_WITH_CHANGES,CONFIRMED"),
    f("event_time", "datetime", "Y"),
    f("trigger_type", "string", "Y", "PO_SENT,SLA_BREACH,ACK_RECEIVED,CHANGE_CREATED,CHANGE_DECIDED"),
    f("trigger_id", "string", "N", rule="ack_id / change_id that caused the transition"),
])

SQL_TYPE = {"string": "TEXT", "int": "INTEGER", "decimal2": "REAL", "decimal4": "REAL",
            "date": "TEXT", "datetime": "TEXT", "bool": "INTEGER"}


def ddl():
    out = ["PRAGMA foreign_keys = ON;", ""]
    for name, t in TABLES.items():
        cols, cons = [], []
        for fd in t["fields"]:
            c = f'  {fd["field"]} {SQL_TYPE[fd["type"]]}'
            if fd["required"] == "Y":
                c += " NOT NULL"
            cols.append(c)
            if fd["uniqueness"] == "PK":
                cons.append(f'  PRIMARY KEY ({fd["field"]})')
            elif fd["uniqueness"] == "UNIQUE":
                cons.append(f'  UNIQUE ({fd["field"]})')
            if fd["fk"]:
                tt, tc = fd["fk"].split(".")
                cons.append(f'  FOREIGN KEY ({fd["field"]}) REFERENCES {tt}({tc})')
            if fd["allowed"] and (fd["type"] == "bool" or fd["type"] == "string"):
                vals = fd["allowed"].split(",")
                if fd["type"] == "bool":
                    lst = ",".join(vals)
                else:
                    lst = ",".join("'%s'" % v for v in vals)
                cons.append(f'  CHECK ({fd["field"]} IN ({lst}))')
        out.append(f"CREATE TABLE {name} (\n" + ",\n".join(cols + cons) + "\n);\n")
    return "\n".join(out)
