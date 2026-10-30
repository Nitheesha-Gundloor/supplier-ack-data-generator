PRAGMA foreign_keys = ON;

CREATE TABLE ApprovalThreshold (
  rule_id TEXT NOT NULL,
  change_type TEXT NOT NULL,
  required_level TEXT NOT NULL,
  metric TEXT NOT NULL,
  lower_exclusive REAL,
  upper_inclusive REAL,
  unit TEXT NOT NULL,
  description TEXT NOT NULL,
  PRIMARY KEY (rule_id),
  CHECK (change_type IN ('DATE','QTY','PRICE','ANY')),
  CHECK (required_level IN ('AUTO','PLANNER','MANAGER','SYSTEM_REJECT')),
  CHECK (unit IN ('days','percent','USD'))
);

CREATE TABLE AppUser (
  user_id TEXT NOT NULL,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL,
  active INTEGER NOT NULL,
  PRIMARY KEY (user_id),
  CHECK (role IN ('PLANNER','OPS_MANAGER','LOGISTICS_ANALYST','WAREHOUSE_OPERATOR')),
  CHECK (active IN (0,1))
);

CREATE TABLE Warehouse (
  warehouse_id TEXT NOT NULL,
  warehouse_name TEXT NOT NULL,
  region TEXT NOT NULL,
  operator_user_id TEXT NOT NULL,
  PRIMARY KEY (warehouse_id),
  FOREIGN KEY (operator_user_id) REFERENCES AppUser(user_id)
);

CREATE TABLE Supplier (
  supplier_id TEXT NOT NULL,
  supplier_name TEXT NOT NULL,
  country TEXT NOT NULL,
  reliability_tier TEXT NOT NULL,
  ack_sla_days INTEGER NOT NULL,
  payment_terms_days INTEGER NOT NULL,
  status TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  PRIMARY KEY (supplier_id),
  CHECK (reliability_tier IN ('A','B','C')),
  CHECK (status IN ('ACTIVE','ON_HOLD'))
);

CREATE TABLE Item (
  item_id TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL,
  uom TEXT NOT NULL,
  pack_size INTEGER NOT NULL,
  standard_cost REAL NOT NULL,
  planning_lead_time_days INTEGER NOT NULL,
  PRIMARY KEY (item_id),
  CHECK (category IN ('RAW','COMPONENT','PACKAGING','FG')),
  CHECK (uom IN ('EA','KG','L'))
);

CREATE TABLE PurchaseOrder (
  po_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  warehouse_id TEXT NOT NULL,
  planner_id TEXT NOT NULL,
  order_date TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  ack_due_at TEXT NOT NULL,
  currency TEXT NOT NULL,
  line_count INTEGER NOT NULL,
  po_total_value REAL NOT NULL,
  current_status TEXT NOT NULL,
  PRIMARY KEY (po_id),
  FOREIGN KEY (supplier_id) REFERENCES Supplier(supplier_id),
  FOREIGN KEY (warehouse_id) REFERENCES Warehouse(warehouse_id),
  FOREIGN KEY (planner_id) REFERENCES AppUser(user_id),
  CHECK (currency IN ('USD')),
  CHECK (current_status IN ('SENT','NO_RESPONSE','CHANGE_PENDING_APPROVAL','SUPPLIER_REJECTED','PARTIALLY_CONFIRMED','CONFIRMED_WITH_CHANGES','CONFIRMED'))
);

CREATE TABLE POLine (
  po_line_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  item_id TEXT NOT NULL,
  ordered_qty INTEGER NOT NULL,
  uom TEXT NOT NULL,
  unit_price REAL NOT NULL,
  requested_date TEXT NOT NULL,
  line_value REAL NOT NULL,
  line_status_current TEXT NOT NULL,
  PRIMARY KEY (po_line_id),
  FOREIGN KEY (po_id) REFERENCES PurchaseOrder(po_id),
  FOREIGN KEY (item_id) REFERENCES Item(item_id),
  CHECK (uom IN ('EA','KG','L')),
  CHECK (line_status_current IN ('UNCONFIRMED','CONFIRMED','PARTIALLY_CONFIRMED','REJECTED','CHANGE_PENDING'))
);

CREATE TABLE Acknowledgement (
  ack_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  revision_no INTEGER NOT NULL,
  ack_received_at TEXT NOT NULL,
  channel TEXT NOT NULL,
  ack_status TEXT NOT NULL,
  supersedes_ack_id TEXT,
  is_latest INTEGER NOT NULL,
  accepted_qty_total INTEGER NOT NULL,
  rejected_qty_total INTEGER NOT NULL,
  accepted_value_total REAL NOT NULL,
  PRIMARY KEY (ack_id),
  FOREIGN KEY (po_id) REFERENCES PurchaseOrder(po_id),
  CHECK (channel IN ('EDI','PORTAL','EMAIL')),
  CHECK (ack_status IN ('ACCEPTED','ACCEPTED_WITH_CHANGES','PARTIALLY_ACCEPTED','REJECTED')),
  FOREIGN KEY (supersedes_ack_id) REFERENCES Acknowledgement(ack_id),
  CHECK (is_latest IN (0,1))
);

CREATE TABLE PromiseDate (
  promise_id TEXT NOT NULL,
  ack_id TEXT NOT NULL,
  po_line_id TEXT NOT NULL,
  accepted_qty INTEGER NOT NULL,
  rejected_qty INTEGER NOT NULL,
  line_ack_status TEXT NOT NULL,
  promised_date TEXT,
  promised_unit_price REAL NOT NULL,
  reason_code TEXT,
  date_delta_days INTEGER,
  price_delta_pct REAL NOT NULL,
  PRIMARY KEY (promise_id),
  FOREIGN KEY (ack_id) REFERENCES Acknowledgement(ack_id),
  FOREIGN KEY (po_line_id) REFERENCES POLine(po_line_id),
  CHECK (line_ack_status IN ('ACCEPTED','PARTIALLY_ACCEPTED','REJECTED')),
  CHECK (reason_code IN ('CAPACITY','MATERIAL_SHORTAGE','QUALITY_HOLD','DISCONTINUED','LOGISTICS','PRICE_ADJUSTMENT'))
);

CREATE TABLE ChangeRequest (
  change_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  po_line_id TEXT NOT NULL,
  source_ack_id TEXT NOT NULL,
  revision_no INTEGER NOT NULL,
  change_type TEXT NOT NULL,
  requested_value TEXT NOT NULL,
  proposed_value TEXT NOT NULL,
  delta_vs_requested REAL NOT NULL,
  delta_pct REAL,
  line_value_impact_usd REAL NOT NULL,
  threshold_rule_id TEXT NOT NULL,
  required_level TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  closed_at TEXT,
  has_downstream_impact INTEGER NOT NULL,
  PRIMARY KEY (change_id),
  FOREIGN KEY (po_id) REFERENCES PurchaseOrder(po_id),
  FOREIGN KEY (po_line_id) REFERENCES POLine(po_line_id),
  FOREIGN KEY (source_ack_id) REFERENCES Acknowledgement(ack_id),
  CHECK (change_type IN ('DATE','QTY','PRICE')),
  FOREIGN KEY (threshold_rule_id) REFERENCES ApprovalThreshold(rule_id),
  CHECK (required_level IN ('AUTO','PLANNER','MANAGER','SYSTEM_REJECT')),
  CHECK (status IN ('PENDING_APPROVAL','APPROVED','AUTO_APPROVED','REJECTED','SUPERSEDED')),
  CHECK (has_downstream_impact IN (0,1))
);

CREATE TABLE Approval (
  approval_id TEXT NOT NULL,
  change_id TEXT NOT NULL,
  step_no INTEGER NOT NULL,
  approver_role TEXT NOT NULL,
  approver_user_id TEXT,
  decision TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  reason_code TEXT NOT NULL,
  PRIMARY KEY (approval_id),
  FOREIGN KEY (change_id) REFERENCES ChangeRequest(change_id),
  CHECK (approver_role IN ('SYSTEM','PLANNER','OPS_MANAGER')),
  FOREIGN KEY (approver_user_id) REFERENCES AppUser(user_id),
  CHECK (decision IN ('APPROVED','REJECTED','PENDING','SUPERSEDED')),
  CHECK (reason_code IN ('WITHIN_TOLERANCE','DOWNSTREAM_IMPACT_ACCEPTED','DOWNSTREAM_IMPACT_UNACCEPTABLE','PRICE_NOT_JUSTIFIED','INVALID_DATE','NEWER_REVISION_RECEIVED','PENDING_REVIEW'))
);

CREATE TABLE InventoryPlan (
  plan_event_id TEXT NOT NULL,
  po_line_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  warehouse_id TEXT NOT NULL,
  version_no INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  source_change_id TEXT,
  projected_qty INTEGER NOT NULL,
  projected_date TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  is_current INTEGER NOT NULL,
  PRIMARY KEY (plan_event_id),
  FOREIGN KEY (po_line_id) REFERENCES POLine(po_line_id),
  FOREIGN KEY (item_id) REFERENCES Item(item_id),
  FOREIGN KEY (warehouse_id) REFERENCES Warehouse(warehouse_id),
  CHECK (event_type IN ('INITIAL','CHANGE_APPLIED')),
  FOREIGN KEY (source_change_id) REFERENCES ChangeRequest(change_id),
  CHECK (is_current IN (0,1))
);

CREATE TABLE ProductionOrder (
  prod_order_id TEXT NOT NULL,
  warehouse_id TEXT NOT NULL,
  owner_planner_id TEXT NOT NULL,
  finished_item_id TEXT NOT NULL,
  planned_start_date TEXT NOT NULL,
  planned_qty INTEGER NOT NULL,
  priority TEXT NOT NULL,
  schedule_status TEXT NOT NULL,
  PRIMARY KEY (prod_order_id),
  FOREIGN KEY (warehouse_id) REFERENCES Warehouse(warehouse_id),
  FOREIGN KEY (owner_planner_id) REFERENCES AppUser(user_id),
  FOREIGN KEY (finished_item_id) REFERENCES Item(item_id),
  CHECK (priority IN ('HIGH','NORMAL','LOW')),
  CHECK (schedule_status IN ('ON_TRACK','AT_RISK','RELEASED','DELAYED'))
);

CREATE TABLE ProductionOrderSupply (
  supply_link_id TEXT NOT NULL,
  prod_order_id TEXT NOT NULL,
  po_line_id TEXT NOT NULL,
  required_qty INTEGER NOT NULL,
  required_date TEXT NOT NULL,
  PRIMARY KEY (supply_link_id),
  FOREIGN KEY (prod_order_id) REFERENCES ProductionOrder(prod_order_id),
  FOREIGN KEY (po_line_id) REFERENCES POLine(po_line_id)
);

CREATE TABLE ChangeImpact (
  impact_id TEXT NOT NULL,
  change_id TEXT NOT NULL,
  prod_order_id TEXT NOT NULL,
  supply_link_id TEXT NOT NULL,
  impact_type TEXT NOT NULL,
  days_late INTEGER,
  shortage_qty INTEGER,
  evaluated_at TEXT NOT NULL,
  PRIMARY KEY (impact_id),
  FOREIGN KEY (change_id) REFERENCES ChangeRequest(change_id),
  FOREIGN KEY (prod_order_id) REFERENCES ProductionOrder(prod_order_id),
  FOREIGN KEY (supply_link_id) REFERENCES ProductionOrderSupply(supply_link_id),
  CHECK (impact_type IN ('LATE_SUPPLY','SHORT_SUPPLY'))
);

CREATE TABLE Notification (
  notification_id TEXT NOT NULL,
  notification_type TEXT NOT NULL,
  recipient_user_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  change_id TEXT,
  prod_order_id TEXT,
  severity TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  message TEXT NOT NULL,
  PRIMARY KEY (notification_id),
  CHECK (notification_type IN ('APPROVAL_REQUIRED','CHANGE_REJECTED','SCHEDULE_IMPACT','INBOUND_RESCHEDULE','SUPPLIER_SILENCE')),
  FOREIGN KEY (recipient_user_id) REFERENCES AppUser(user_id),
  FOREIGN KEY (po_id) REFERENCES PurchaseOrder(po_id),
  FOREIGN KEY (change_id) REFERENCES ChangeRequest(change_id),
  FOREIGN KEY (prod_order_id) REFERENCES ProductionOrder(prod_order_id),
  CHECK (severity IN ('INFO','WARNING','CRITICAL'))
);

CREATE TABLE POStatusHistory (
  po_status_event_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  event_time TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  trigger_id TEXT,
  PRIMARY KEY (po_status_event_id),
  FOREIGN KEY (po_id) REFERENCES PurchaseOrder(po_id),
  CHECK (to_status IN ('SENT','NO_RESPONSE','CHANGE_PENDING_APPROVAL','SUPPLIER_REJECTED','PARTIALLY_CONFIRMED','CONFIRMED_WITH_CHANGES','CONFIRMED')),
  CHECK (trigger_type IN ('PO_SENT','SLA_BREACH','ACK_RECEIVED','CHANGE_CREATED','CHANGE_DECIDED'))
);
