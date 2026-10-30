#!/usr/bin/env python3
"""Supplier acknowledgement / promise-date / change / schedule-impact synthetic data generator.

Usage:  python generate_data.py --seed 20261022 --scale 1.0 --out data_full
Scale 1.0 => 10,000 POs and 15,000 acknowledgement revisions.  Same code path for any scale.
Deterministic: only random.Random(seed) is used; no wall-clock values are written.
"""
import argparse, csv, hashlib, json, math, os, random
from collections import defaultdict
from datetime import date, datetime, timedelta, time

import schema_def as S

AS_OF = datetime(2026, 10, 22, 18, 0, 0)
GEN_VERSION = "1.0.0"
RATE = dict(unapproved=0.005, wrong_line=0.005, date_before_order=0.005, stale_overwrite=0.004)

TIER = {  # per-line behaviour probabilities by supplier reliability tier
    "A": dict(p_silent=.02, p_slow=.02, p_date=.06, p_qty=.025, p_rej=.004, p_price=.015, revw=.6, sla=2),
    "B": dict(p_silent=.06, p_slow=.08, p_date=.15, p_qty=.06, p_rej=.012, p_price=.03, revw=1.0, sla=3),
    "C": dict(p_silent=.14, p_slow=.20, p_date=.32, p_qty=.14, p_rej=.03, p_price=.07, revw=1.6, sla=3),
}
LEVEL_RANK = {"AUTO": 0, "PLANNER": 1, "MANAGER": 2}


def hours(rng, med, sig, lo, hi):
    return min(hi, max(lo, rng.lognormvariate(math.log(med), sig)))


def td_h(h):
    return timedelta(seconds=int(h * 3600))


def level_for(ctype, metric):
    if ctype == "DATE":
        a = abs(metric)
        return ("THR-DATE-1", "AUTO") if a <= 3 else ("THR-DATE-2", "PLANNER") if a <= 14 else ("THR-DATE-3", "MANAGER")
    if ctype == "QTY":
        return ("THR-QTY-1", "AUTO") if metric <= 5 else ("THR-QTY-2", "PLANNER") if metric <= 20 else ("THR-QTY-3", "MANAGER")
    a = abs(metric)
    return ("THR-PRC-1", "AUTO") if a <= 2 else ("THR-PRC-2", "PLANNER") if a <= 10 else ("THR-PRC-3", "MANAGER")


# ----------------------------------------------------------------------------------------------
def generate(seed, scale):
    rng = random.Random(seed)
    n_po = max(20, round(10000 * scale))
    n_ack_target = round(1.5 * n_po)
    T = {}

    # ---- reference tables -------------------------------------------------------------------
    T["ApprovalThreshold"] = [
        dict(rule_id="THR-DATE-1", change_type="DATE", required_level="AUTO", metric="abs_days", lower_exclusive=None, upper_inclusive=3, unit="days", description="Date change within 3 days of requested date is auto-approved"),
        dict(rule_id="THR-DATE-2", change_type="DATE", required_level="PLANNER", metric="abs_days", lower_exclusive=3, upper_inclusive=14, unit="days", description="Date change of 4-14 days needs planner approval"),
        dict(rule_id="THR-DATE-3", change_type="DATE", required_level="MANAGER", metric="abs_days", lower_exclusive=14, upper_inclusive=None, unit="days", description="Date change over 14 days needs planner endorsement + ops manager approval"),
        dict(rule_id="THR-QTY-1", change_type="QTY", required_level="AUTO", metric="shortfall_pct", lower_exclusive=None, upper_inclusive=5, unit="percent", description="Quantity shortfall up to 5% of ordered qty is auto-approved"),
        dict(rule_id="THR-QTY-2", change_type="QTY", required_level="PLANNER", metric="shortfall_pct", lower_exclusive=5, upper_inclusive=20, unit="percent", description="Shortfall of 5-20% needs planner approval"),
        dict(rule_id="THR-QTY-3", change_type="QTY", required_level="MANAGER", metric="shortfall_pct", lower_exclusive=20, upper_inclusive=None, unit="percent", description="Shortfall over 20% needs planner endorsement + ops manager approval"),
        dict(rule_id="THR-PRC-1", change_type="PRICE", required_level="AUTO", metric="abs_price_pct", lower_exclusive=None, upper_inclusive=2, unit="percent", description="Price change within 2% is auto-approved"),
        dict(rule_id="THR-PRC-2", change_type="PRICE", required_level="PLANNER", metric="abs_price_pct", lower_exclusive=2, upper_inclusive=10, unit="percent", description="Price change of 2-10% needs planner approval"),
        dict(rule_id="THR-PRC-3", change_type="PRICE", required_level="MANAGER", metric="abs_price_pct", lower_exclusive=10, upper_inclusive=None, unit="percent", description="Price change over 10% needs planner endorsement + ops manager approval"),
        dict(rule_id="THR-VAL-1", change_type="ANY", required_level="MANAGER", metric="abs_line_value_usd", lower_exclusive=50000, upper_inclusive=None, unit="USD", description="Any change moving line value by more than USD 50,000 escalates to ops manager"),
        dict(rule_id="THR-SAN-1", change_type="DATE", required_level="SYSTEM_REJECT", metric="date_vs_order_date", lower_exclusive=None, upper_inclusive=0, unit="days", description="Proposed date earlier than PO order date is rejected by the system"),
    ]

    first = ["Alex", "Sam", "Priya", "Chen", "Maria", "Omar", "Lena", "Ravi", "Noah", "Aiko", "Tomas", "Fatima", "Jon", "Ines", "Kofi", "Mei", "Luis", "Anya", "Dev", "Zoe"]
    last = ["Rao", "Silva", "Novak", "Kim", "Okafor", "Meyer", "Haddad", "Lopez", "Tan", "Ivanov", "Bauer", "Patel", "Cohen", "Nguyen", "Rossi", "Sato", "Evans", "Costa", "Khan", "Berg"]

    users = []
    def add_users(prefix, base, n, role):
        ids = []
        for i in range(n):
            uid = f"USR-{base + i:03d}"
            users.append(dict(user_id=uid, full_name=f"{rng.choice(first)} {rng.choice(last)}", role=role, active=1))
            ids.append(uid)
        return ids
    planners = add_users("P", 1, 24, "PLANNER")
    managers = add_users("M", 101, 4, "OPS_MANAGER")
    analysts = add_users("L", 201, 4, "LOGISTICS_ANALYST")
    operators = add_users("W", 301, 6, "WAREHOUSE_OPERATOR")
    T["AppUser"] = users

    regions = ["NA-East", "NA-West", "EU-Central", "EU-South", "APAC-South", "APAC-East"]
    warehouses = [dict(warehouse_id=f"WH-{i + 1:02d}", warehouse_name=f"Warehouse {regions[i]}", region=regions[i], operator_user_id=operators[i]) for i in range(6)]
    T["Warehouse"] = warehouses
    wh_ids = [w["warehouse_id"] for w in warehouses]
    wh_idx = {w: i for i, w in enumerate(wh_ids)}
    wh_w = [.22, .18, .2, .15, .13, .12]

    n_sup = max(10, min(80, round(80 * scale ** 0.5)))
    countries = ["DE", "CN", "US", "MX", "IN", "PL", "VN", "TR", "KR", "IT"]
    suppliers = []
    for i in range(n_sup):
        tier = rng.choices(["A", "B", "C"], [.2, .5, .3])[0]
        suppliers.append(dict(supplier_id=f"SUP-{i + 1:04d}", supplier_name=f"Supplier {i + 1:04d} Ltd", country=rng.choice(countries),
                              reliability_tier=tier, ack_sla_days=TIER[tier]["sla"], payment_terms_days=rng.choice([30, 45, 60]),
                              status="ACTIVE" if rng.random() > .03 else "ON_HOLD", effective_from=date(2025, rng.randint(1, 12), rng.randint(1, 28)),
                              _planner=planners[i % len(planners)]))
    T["Supplier"] = suppliers
    sup_w = [1 / (i + 1) ** 0.5 for i in range(n_sup)]

    items = []
    for i in range(400):
        cat = "FG" if i < 60 else rng.choices(["RAW", "COMPONENT", "PACKAGING"], [.36, .47, .17])[0]
        uom = rng.choice(["KG", "L", "EA"]) if cat == "RAW" else "EA"
        items.append(dict(item_id=f"ITM-{i + 1:04d}", description=f"{cat.title()} item {i + 1:04d}", category=cat, uom=uom,
                          pack_size=rng.choice([1, 10, 12, 24, 50, 100]), standard_cost=round(rng.lognormvariate(math.log(14), .9), 2) + 0.05,
                          planning_lead_time_days=rng.randint(10, 55)))
    T["Item"] = items
    item_by_id = {i["item_id"]: i for i in items}
    fg_items = [i for i in items if i["category"] == "FG"]
    comp_items = [i for i in items if i["category"] != "FG"]

    # ---- purchase orders & lines ------------------------------------------------------------
    weekdays = []
    d = date(2026, 1, 2)
    while d <= date(2026, 10, 20):
        if d.weekday() < 5:
            weekdays.append(d)
        d += timedelta(days=1)
    dates = sorted(rng.choice(weekdays) for _ in range(n_po))
    pos, lines = [], []
    po_by_id, line_by_id, lines_of_po = {}, {}, defaultdict(list)
    for i, d in enumerate(dates, 1):
        po_id = f"PO-2026-{i:06d}"
        sup = rng.choices(suppliers, weights=sup_w)[0]
        sent = datetime.combine(d, time(8, 0)) + timedelta(seconds=rng.randint(0, 9 * 3600))
        po = dict(po_id=po_id, supplier_id=sup["supplier_id"], warehouse_id=rng.choices(wh_ids, wh_w)[0],
                  planner_id=sup["_planner"] if rng.random() < .85 else rng.choice(planners), order_date=d, sent_at=sent,
                  ack_due_at=sent + timedelta(days=sup["ack_sla_days"]), currency="USD", _sup=sup)
        n_l = rng.choices([1, 2, 3, 4, 5], [30, 30, 20, 12, 8])[0]
        for ln, it in enumerate(rng.sample(comp_items, n_l), 1):
            base = rng.lognormvariate(math.log(400), .9)
            qty = max(it["pack_size"], int(round(base / it["pack_size"])) * it["pack_size"])
            qty = min(qty, 50000)
            price = max(0.05, round(it["standard_cost"] * rng.uniform(.92, 1.08), 2))
            ln_row = dict(po_line_id=f"{po_id}-L{ln:02d}", po_id=po_id, line_no=ln, item_id=it["item_id"], ordered_qty=qty, uom=it["uom"],
                          unit_price=price, requested_date=d + timedelta(days=it["planning_lead_time_days"] + rng.randint(0, 10)),
                          line_value=round(qty * price, 2))
            lines.append(ln_row); lines_of_po[po_id].append(ln_row); line_by_id[ln_row["po_line_id"]] = ln_row
        po["line_count"] = n_l
        po["po_total_value"] = round(sum(l["line_value"] for l in lines_of_po[po_id]), 2)
        pos.append(po); po_by_id[po_id] = po

    # ---- supplier behaviour: silence, first-ack time, revision counts ----------------------
    responders = []
    for po in pos:
        tp = TIER[po["_sup"]["reliability_tier"]]
        silent = rng.random() < tp["p_silent"]
        h = rng.uniform(96, 192) if rng.random() < tp["p_slow"] else hours(rng, 20, .5, 2, 70)
        t1 = po["sent_at"] + td_h(h)
        po["_silent"] = silent
        po["_t1"] = t1
        if (not silent) and t1 <= AS_OF:
            responders.append(po)
    cutoff = AS_OF - timedelta(days=70)
    elig = [po for po in responders if po["sent_at"] <= cutoff]
    target_extra = max(0, n_ack_target - len(responders))
    extras = {}
    if elig:
        ws = [TIER[p["_sup"]["reliability_tier"]]["revw"] for p in elig]
        goal = target_extra / len(elig)
        lo, hi = 0.0, 5.0
        for _ in range(40):
            mid = (lo + hi) / 2
            m = sum((lambda q: sum(q ** i for i in range(1, 6)))(min(.65, mid * w)) for w in ws) / len(ws)
            lo, hi = (mid, hi) if m < goal else (lo, mid)
        fac = (lo + hi) / 2
        for p, w in zip(elig, ws):
            k, q = 0, min(.65, fac * w)
            for _ in range(5):
                if rng.random() < q:
                    k += 1
                else:
                    break
            extras[p["po_id"]] = k
        tot = sum(extras.values())
        order = [p["po_id"] for p in elig]
        while tot > target_extra:
            pid = rng.choice(order)
            if extras[pid] > 0:
                extras[pid] -= 1; tot -= 1
        while tot < target_extra and any(extras[x] < 5 for x in order):
            pid = rng.choice(order)
            if extras[pid] < 5:
                extras[pid] += 1; tot += 1

    # ---- acknowledgements and promises -------------------------------------------------------
    acks, promises = [], []
    acks_of_po = defaultdict(list)
    promises_of_ack = defaultdict(list)
    channels = ["EDI", "PORTAL", "EMAIL"]

    def sample_short(ordered):
        r = rng.random()
        pct = rng.uniform(.01, .05) if r < .5 else rng.uniform(.05, .20) if r < .85 else rng.uniform(.20, .60)
        acc = int(ordered * (1 - pct))
        if acc >= ordered:
            acc = ordered - 1
        return max(1, acc)

    def sample_date_delta():
        if rng.random() < .12:
            return -rng.randint(1, 5)
        b = rng.choices([0, 1, 2], [.55, .35, .10])[0]
        return [rng.randint(1, 3), rng.randint(4, 14), rng.randint(15, 45)][b]

    def sample_price(unit):
        r = rng.random()
        pct = rng.uniform(.005, .02) if r < .6 else rng.uniform(.02, .10) if r < .9 else rng.uniform(.10, .20)
        sign = 1 if rng.random() < .75 else -1
        p = round(unit * (1 + sign * pct), 2)
        return p if p != unit else round(unit + .01, 2)

    def initial_state(line, tp):
        st = dict(acc=line["ordered_qty"], date=line["requested_date"], price=line["unit_price"], carry=line["requested_date"])
        if rng.random() < tp["p_rej"]:
            st["acc"], st["date"] = 0, None
            return st
        if line["ordered_qty"] >= 2 and rng.random() < tp["p_qty"]:
            st["acc"] = sample_short(line["ordered_qty"])
        if rng.random() < tp["p_date"]:
            st["date"] = line["requested_date"] + timedelta(days=sample_date_delta())
        if rng.random() < tp["p_price"]:
            st["price"] = sample_price(line["unit_price"])
        if st["date"]:
            st["carry"] = st["date"]
        return st

    def revise(st, line, tp):
        n = dict(st)
        ordered, req = line["ordered_qty"], line["requested_date"]
        if st["acc"] == 0:
            if rng.random() < .25:
                n["acc"] = max(1, int(ordered * rng.uniform(.5, 1)))
                n["date"] = req + timedelta(days=rng.randint(7, 28))
        elif st["acc"] < ordered:
            r = rng.random()
            if r < .45:
                n["acc"] = ordered if rng.random() < .5 else min(ordered, st["acc"] + max(1, int((ordered - st["acc"]) * rng.uniform(.3, .8))))
            elif r < .48:
                n["acc"] = int(st["acc"] * rng.uniform(.5, .95))
        elif ordered >= 2 and rng.random() < .03:
            n["acc"] = sample_short(ordered)
        if n["acc"] == 0:
            n["date"] = None
        elif n["date"] is not None and st["acc"] > 0 and rng.random() < .25:
            r = rng.random()
            cur = st["date"]
            if r < .55:
                n["date"] = cur + timedelta(days=rng.randint(1, 10))
            elif r < .85:
                n["date"] = max(req, cur - timedelta(days=rng.randint(2, 10)))
            else:
                n["date"] = req - timedelta(days=rng.randint(1, 4))
        if rng.random() < .04:
            n["price"] = round(st["price"] * (1 + rng.uniform(-.02, .06)), 2)
        if n["date"]:
            n["carry"] = n["date"]
        return n

    def force_change(n, st, line):
        if n["acc"] > 0 and n["date"] is not None:
            n["date"] = n["date"] + timedelta(days=rng.choice([2, 5, 9, -2]))
        elif n["acc"] == 0:
            n["acc"] = line["ordered_qty"]
            n["date"] = line["requested_date"] + timedelta(days=rng.randint(7, 21))
        else:
            n["date"] = st["carry"] + timedelta(days=3)
        n["carry"] = n["date"]

    def reason_for(st, line):
        if st["acc"] == 0:
            return rng.choices(["DISCONTINUED", "CAPACITY", "MATERIAL_SHORTAGE"], [.2, .4, .4])[0]
        if st["acc"] < line["ordered_qty"]:
            return rng.choice(["CAPACITY", "MATERIAL_SHORTAGE", "QUALITY_HOLD"])
        if st["date"] != line["requested_date"]:
            return rng.choice(["LOGISTICS", "CAPACITY"])
        if st["price"] != line["unit_price"]:
            return "PRICE_ADJUSTMENT"
        return None

    resp_ids = {p["po_id"] for p in responders}
    for po in pos:
        if po["po_id"] not in resp_ids:
            continue
        n_rev = 1 + extras.get(po["po_id"], 0)
        tp = TIER[po["_sup"]["reliability_tier"]]
        t = po["_t1"]
        prev_states, prev_ack = None, None
        for rev in range(1, n_rev + 1):
            if rev > 1:
                t = t + td_h(hours(rng, 36, .7, 6, 9 * 24))
            ack_id = f"ACK-{po['po_id']}-{rev:02d}"
            if rev == 1:
                states = [initial_state(l, tp) for l in lines_of_po[po["po_id"]]]
            else:
                states, changed = [], False
                for l, st in zip(lines_of_po[po["po_id"]], prev_states):
                    n = revise(st, l, tp)
                    changed |= (n["acc"], n["date"], n["price"]) != (st["acc"], st["date"], st["price"])
                    states.append(n)
                if not changed:
                    k = rng.randrange(len(states))
                    force_change(states[k], prev_states[k], lines_of_po[po["po_id"]][k])
            tot_acc = tot_rej = 0
            val = 0.0
            line_stats, any_diff = [], False
            for l, st in zip(lines_of_po[po["po_id"]], states):
                rej = l["ordered_qty"] - st["acc"]
                ls = "ACCEPTED" if rej == 0 else "REJECTED" if st["acc"] == 0 else "PARTIALLY_ACCEPTED"
                line_stats.append(ls)
                any_diff |= (st["date"] != l["requested_date"]) or (st["price"] != l["unit_price"])
                tot_acc += st["acc"]; tot_rej += rej; val += st["acc"] * st["price"]
                pr = dict(promise_id=f"PRM-{ack_id}-L{l['line_no']:02d}", ack_id=ack_id, po_line_id=l["po_line_id"], accepted_qty=st["acc"],
                          rejected_qty=rej, line_ack_status=ls, promised_date=st["date"], promised_unit_price=st["price"],
                          reason_code=reason_for(st, l),
                          date_delta_days=(st["date"] - l["requested_date"]).days if st["date"] else None,
                          price_delta_pct=round((st["price"] / l["unit_price"] - 1) * 100, 4), _line=l)
                promises.append(pr); promises_of_ack[ack_id].append(pr)
            if all(s == "ACCEPTED" for s in line_stats):
                astat = "ACCEPTED_WITH_CHANGES" if any_diff else "ACCEPTED"
            elif all(s == "REJECTED" for s in line_stats):
                astat = "REJECTED"
            else:
                astat = "PARTIALLY_ACCEPTED"
            ack = dict(ack_id=ack_id, po_id=po["po_id"], revision_no=rev, ack_received_at=t, channel=rng.choices(channels, [.5, .3, .2])[0],
                       ack_status=astat, supersedes_ack_id=prev_ack, is_latest=1 if rev == n_rev else 0, accepted_qty_total=tot_acc,
                       rejected_qty_total=tot_rej, accepted_value_total=round(val, 2))
            acks.append(ack); acks_of_po[po["po_id"]].append(ack)
            prev_states, prev_ack = states, ack_id
    ack_by_id = {a["ack_id"]: a for a in acks}

    # ---- production orders and supply links (N:M bridge) -----------------------------------
    prods, links = [], []
    links_by_line = defaultdict(list)
    open_by_wh = defaultdict(list)
    for po in pos:
        for l in lines_of_po[po["po_id"]]:
            nl = rng.choices([0, 1, 2], [.35, .45, .2])[0]
            fr = [] if nl == 0 else [rng.uniform(.5, 1)] if nl == 1 else [rng.uniform(.3, .6), rng.uniform(.2, .4)]
            for frac in fr:
                req_d = l["requested_date"] + timedelta(days=rng.choices([0, 1, 2, 3, 5, 7, 10], [10, 15, 20, 20, 15, 10, 10])[0])
                pool = open_by_wh[po["warehouse_id"]]
                target = None
                if pool and rng.random() < .3:
                    cand = pool[-rng.randint(1, min(len(pool), 20))]
                    if cand["_nl"] < 3 and cand["planned_start_date"] - timedelta(days=1) >= l["requested_date"] and \
                            all(lk["po_line_id"] != l["po_line_id"] for lk in cand["_links"]):
                        target = cand
                if target is None:
                    target = dict(prod_order_id=f"PRD-2026-{len(prods) + 1:06d}", warehouse_id=po["warehouse_id"], owner_planner_id=po["planner_id"],
                                  finished_item_id=rng.choice(fg_items)["item_id"], planned_start_date=req_d + timedelta(days=rng.randint(1, 3)),
                                  planned_qty=max(10, int(rng.lognormvariate(math.log(300), .8))),
                                  priority=rng.choices(["HIGH", "NORMAL", "LOW"], [.15, .65, .2])[0], _nl=0, _links=[])
                    prods.append(target); pool.append(target)
                    rd = req_d
                else:
                    rd = target["planned_start_date"] - timedelta(days=1)
                lk = dict(supply_link_id=f"PSL-{len(links) + 1:06d}", prod_order_id=target["prod_order_id"], po_line_id=l["po_line_id"],
                          required_qty=max(1, int(l["ordered_qty"] * frac)), required_date=rd, _prod=target)
                target["_nl"] += 1; target["_links"].append(lk)
                links.append(lk); links_by_line[l["po_line_id"]].append(lk)
    for v in links_by_line.values():
        v.sort(key=lambda x: (x["required_date"], x["supply_link_id"]))

    # ---- inject source-record anomalies (before derivations) --------------------------------
    gt = []  # internal ground truth records
    rows_sorted = sorted(promises, key=lambda p: p["promise_id"])
    n_wrong = max(2, round(RATE["wrong_line"] * n_po))
    n_early = max(2, round(RATE["date_before_order"] * n_po))
    used_ack = set()
    for a in rng.sample(sorted(ack_by_id), min(n_wrong, len(ack_by_id))):
        ack = ack_by_id[a]
        other = rng.choice(pos)
        while other["po_id"] == ack["po_id"]:
            other = rng.choice(pos)
        lb = rng.choice(lines_of_po[other["po_id"]])
        pr = dict(promise_id=f"PRM-{a}-X01", ack_id=a, po_line_id=lb["po_line_id"], accepted_qty=lb["ordered_qty"], rejected_qty=0,
                  line_ack_status="ACCEPTED", promised_date=lb["requested_date"], promised_unit_price=lb["unit_price"], reason_code=None,
                  date_delta_days=0, price_delta_pct=0.0, _line=lb, _wrong=True)
        promises.append(pr); promises_of_ack[a].append(pr); used_ack.add(a)
        gt.append(dict(issue_type="ACK_REFERS_WRONG_PO_LINE", entity="PromiseDate", key=pr, related=f"{a}|{lb['po_line_id']}",
                       po_id=ack["po_id"], rule="promise.po_line.po_id <> acknowledgement.po_id", decision="QUARANTINE_ROW",
                       notes="Promise row on this acknowledgement points to a line of a different PO; excluded from change derivation."))
    cand = [p for p in rows_sorted if p["promised_date"] is not None and p["ack_id"] not in used_ack]
    for pr in rng.sample(cand, min(n_early, len(cand))):
        po = po_by_id[ack_by_id[pr["ack_id"]]["po_id"]]
        pr["promised_date"] = po["order_date"] - timedelta(days=rng.randint(1, 20))
        pr["date_delta_days"] = (pr["promised_date"] - pr["_line"]["requested_date"]).days
        pr["_early"] = True
        gt.append(dict(issue_type="PROMISE_DATE_BEFORE_ORDER_DATE", entity="PromiseDate", key=pr, related=f"{pr['ack_id']}|{po['po_id']}",
                       po_id=po["po_id"], rule="promise.promised_date < purchase_order.order_date", decision="REJECT_CHANGE",
                       notes="Promised date precedes PO order date; system rule THR-SAN-1 must reject the resulting change."))

    # derived ack_status is recomputed from the (possibly anomalous) source promise rows (Step 6)
    for a in acks:
        rows = [p for p in promises_of_ack[a["ack_id"]] if not p.get("_wrong")]
        if all(p["line_ack_status"] == "ACCEPTED" for p in rows):
            diff = any(p["promised_date"] != p["_line"]["requested_date"] or p["promised_unit_price"] != p["_line"]["unit_price"] for p in rows)
            a["ack_status"] = "ACCEPTED_WITH_CHANGES" if diff else "ACCEPTED"
        elif all(p["line_ack_status"] == "REJECTED" for p in rows):
            a["ack_status"] = "REJECTED"
        else:
            a["ack_status"] = "PARTIALLY_ACCEPTED"

    # ---- change requests, impacts, approvals, notifications --------------------------------
    crs, approvals, impacts, notifs = [], [], [], []
    crs_by_line = defaultdict(list)
    crs_of_po = defaultdict(list)

    def notif(ntype, recipient, po_id, sent_at, sev, msg, change_id=None, prod_id=None):
        if sent_at <= AS_OF:
            notifs.append(dict(notification_type=ntype, recipient_user_id=recipient, po_id=po_id, change_id=change_id, prod_order_id=prod_id,
                               severity=sev, sent_at=sent_at, message=msg))

    def calc_impacts(ctype, prop, lks):
        res = []
        if ctype == "DATE":
            for lk in lks:
                if prop > lk["required_date"]:
                    res.append((lk, "LATE_SUPPLY", (prop - lk["required_date"]).days, None))
        elif ctype == "QTY":
            cum = 0
            for lk in lks:
                cum += lk["required_qty"]
                if cum > prop:
                    res.append((lk, "SHORT_SUPPLY", None, min(lk["required_qty"], cum - prop)))
        return res

    for po in pos:
        acks_p = acks_of_po.get(po["po_id"], [])
        if not acks_p:
            continue
        tier = po["_sup"]["reliability_tier"]
        st = {}
        for l in lines_of_po[po["po_id"]]:
            st[(l["po_line_id"], "DATE")] = dict(last=l["requested_date"], force=l["requested_date"], status=None)
            st[(l["po_line_id"], "QTY")] = dict(last=l["ordered_qty"], force=l["ordered_qty"], status=None)
            st[(l["po_line_id"], "PRICE")] = dict(last=l["unit_price"], force=l["unit_price"], status=None)
        cnt = 0
        for ri, ack in enumerate(acks_p):
            next_t = acks_p[ri + 1]["ack_received_at"] if ri + 1 < len(acks_p) else None
            created = ack["ack_received_at"] + timedelta(seconds=60)
            for pr in sorted(promises_of_ack[ack["ack_id"]], key=lambda x: x["promise_id"]):
                if pr.get("_wrong"):
                    continue
                l = pr["_line"]
                cand_changes = []
                if pr["promised_date"] is not None:
                    cand_changes.append(("DATE", pr["promised_date"]))
                cand_changes.append(("QTY", pr["accepted_qty"]))
                cand_changes.append(("PRICE", pr["promised_unit_price"]))
                for ctype, prop in cand_changes:
                    s = st[(l["po_line_id"], ctype)]
                    if not (prop != s["last"] or (s["status"] == "SUPERSEDED" and prop != s["force"])):
                        continue
                    cnt += 1
                    change_id = f"CHG-{po['po_id']}-{cnt:06d}"
                    if ctype == "DATE":
                        req_v, delta, dpct = l["requested_date"], (prop - l["requested_date"]).days, None
                        vimp = 0.0
                        rid, lvl = level_for("DATE", delta)
                        reqs, props = req_v.isoformat(), prop.isoformat()
                    elif ctype == "QTY":
                        req_v, delta = l["ordered_qty"], prop - l["ordered_qty"]
                        dpct = round((l["ordered_qty"] - prop) / l["ordered_qty"] * 100, 4)
                        vimp = round(delta * l["unit_price"], 2)
                        rid, lvl = level_for("QTY", dpct)
                        reqs, props = str(req_v), str(prop)
                    else:
                        req_v, delta = l["unit_price"], round(prop - l["unit_price"], 2)
                        dpct = round((prop / l["unit_price"] - 1) * 100, 4)
                        vimp = round(delta * pr["accepted_qty"], 2)
                        rid, lvl = level_for("PRICE", dpct)
                        reqs, props = f"{req_v:.2f}", f"{prop:.2f}"
                    if abs(vimp) > 50000 and LEVEL_RANK[lvl] < 2:
                        rid, lvl = "THR-VAL-1", "MANAGER"
                    if ctype == "DATE" and prop < po["order_date"]:
                        rid, lvl = "THR-SAN-1", "SYSTEM_REJECT"
                    imps = [] if lvl == "SYSTEM_REJECT" else calc_impacts(ctype, prop, links_by_line.get(l["po_line_id"], []))
                    cr = dict(change_id=change_id, po_id=po["po_id"], po_line_id=l["po_line_id"], source_ack_id=ack["ack_id"], revision_no=ack["revision_no"],
                              change_type=ctype, requested_value=reqs, proposed_value=props, delta_vs_requested=delta, delta_pct=dpct,
                              line_value_impact_usd=vimp, threshold_rule_id=rid, required_level=lvl, created_at=created,
                              has_downstream_impact=1 if imps else 0, _prop=prop, _force_before=s["force"])
                    # --- impacts
                    my_imps = []
                    for lk, itype, dl, sq in imps:
                        my_imps.append(dict(change_id=change_id, prod_order_id=lk["prod_order_id"], supply_link_id=lk["supply_link_id"], impact_type=itype,
                                            days_late=dl, shortage_qty=sq, evaluated_at=created, _lk=lk))
                    impacts.extend(my_imps)
                    # --- decision workflow
                    planner = po["planner_id"]
                    has_hi = any(lk["_prod"]["priority"] == "HIGH" and ((it == "LATE_SUPPLY" and dl > 7) or (it == "SHORT_SUPPLY" and sq > 0)) for lk, it, dl, sq in imps)
                    mgr_bad = bool(imps) and (tier == "C" or any((dl or 0) > 30 for _, _, dl, _ in imps) or
                                              any(it == "SHORT_SUPPLY" and sq / lk["required_qty"] > .5 for lk, it, dl, sq in imps))
                    steps = []
                    def add_step(n, role, user, dec, req_at, dec_at, rc):
                        steps.append(dict(approval_id=f"APR-{change_id}-{n:02d}", change_id=change_id, step_no=n, approver_role=role,
                                          approver_user_id=user, decision=dec, requested_at=req_at, decided_at=dec_at, reason_code=rc))
                    if lvl == "SYSTEM_REJECT":
                        add_step(1, "SYSTEM", None, "REJECTED", created, created, "INVALID_DATE")
                        cr["status"], cr["closed_at"] = "REJECTED", created
                        notif("CHANGE_REJECTED", planner, po["po_id"], created, "WARNING", "Supplier promise rejected: promised date before PO order date", change_id)
                    elif lvl == "AUTO":
                        add_step(1, "SYSTEM", None, "APPROVED", created, created, "WITHIN_TOLERANCE")
                        cr["status"], cr["closed_at"] = "AUTO_APPROVED", created
                    else:
                        stale_p = rng.random() < .04
                        dh = rng.uniform(7 * 24, 40 * 24) if stale_p else hours(rng, 10, .9, 1, 240)
                        t1 = created + td_h(dh)
                        notif("APPROVAL_REQUIRED", planner, po["po_id"], created, "WARNING" if lvl == "MANAGER" else "INFO",
                              f"{ctype} change {change_id} requires planner approval", change_id)
                        if next_t is not None and t1 >= next_t:
                            add_step(1, "PLANNER", planner, "SUPERSEDED", created, next_t, "NEWER_REVISION_RECEIVED")
                            cr["status"], cr["closed_at"] = "SUPERSEDED", next_t
                        elif t1 > AS_OF:
                            add_step(1, "PLANNER", planner, "PENDING", created, None, "PENDING_REVIEW")
                            cr["status"], cr["closed_at"] = "PENDING_APPROVAL", None
                        else:
                            rej = has_hi or (ctype == "PRICE" and dpct > 7)
                            if rej:
                                rc = "DOWNSTREAM_IMPACT_UNACCEPTABLE" if has_hi else "PRICE_NOT_JUSTIFIED"
                                add_step(1, "PLANNER", planner, "REJECTED", created, t1, rc)
                                cr["status"], cr["closed_at"] = "REJECTED", t1
                                notif("CHANGE_REJECTED", planner, po["po_id"], t1, "INFO", f"{ctype} change {change_id} rejected", change_id)
                            else:
                                add_step(1, "PLANNER", planner, "APPROVED", created, t1, "DOWNSTREAM_IMPACT_ACCEPTED" if imps else "WITHIN_TOLERANCE")
                                if lvl == "PLANNER":
                                    cr["status"], cr["closed_at"] = "APPROVED", t1
                                else:
                                    mgr = rng.choice(managers)
                                    stale_m = rng.random() < .03
                                    dm = rng.uniform(7 * 24, 30 * 24) if stale_m else hours(rng, 20, .8, 2, 400)
                                    t2 = t1 + td_h(dm)
                                    notif("APPROVAL_REQUIRED", mgr, po["po_id"], t1, "WARNING", f"{ctype} change {change_id} requires ops-manager approval", change_id)
                                    if next_t is not None and t2 >= next_t:
                                        add_step(2, "OPS_MANAGER", mgr, "SUPERSEDED", t1, next_t, "NEWER_REVISION_RECEIVED")
                                        cr["status"], cr["closed_at"] = "SUPERSEDED", next_t
                                    elif t2 > AS_OF:
                                        add_step(2, "OPS_MANAGER", mgr, "PENDING", t1, None, "PENDING_REVIEW")
                                        cr["status"], cr["closed_at"] = "PENDING_APPROVAL", None
                                    else:
                                        brej = mgr_bad or (ctype == "PRICE" and dpct > 15)
                                        if brej:
                                            add_step(2, "OPS_MANAGER", mgr, "REJECTED", t1, t2,
                                                     "DOWNSTREAM_IMPACT_UNACCEPTABLE" if mgr_bad else "PRICE_NOT_JUSTIFIED")
                                            cr["status"], cr["closed_at"] = "REJECTED", t2
                                            notif("CHANGE_REJECTED", planner, po["po_id"], t2, "INFO", f"{ctype} change {change_id} rejected by ops manager", change_id)
                                        else:
                                            add_step(2, "OPS_MANAGER", mgr, "APPROVED", t1, t2, "DOWNSTREAM_IMPACT_ACCEPTED" if imps else "WITHIN_TOLERANCE")
                                            cr["status"], cr["closed_at"] = "APPROVED", t2
                    approvals.extend(steps)
                    cr["_needs_human"] = lvl in ("PLANNER", "MANAGER")
                    # --- notifications on approval
                    if cr["status"] in ("APPROVED", "AUTO_APPROVED"):
                        tc = cr["closed_at"]
                        for im in my_imps:
                            prod = im["_lk"]["_prod"]
                            sev = "CRITICAL" if prod["priority"] == "HIGH" else "WARNING"
                            msg = f"{ctype} change {change_id} approved: {im['impact_type']} on {prod['prod_order_id']}"
                            notif("SCHEDULE_IMPACT", prod["owner_planner_id"], po["po_id"], tc, sev, msg, change_id, prod["prod_order_id"])
                            if sev == "CRITICAL":
                                notif("SCHEDULE_IMPACT", analysts[wh_idx[po["warehouse_id"]] % len(analysts)], po["po_id"], tc, sev, msg, change_id, prod["prod_order_id"])
                        if ctype in ("DATE", "QTY") and prop != cr["_force_before"]:
                            notif("INBOUND_RESCHEDULE", warehouses[wh_idx[po["warehouse_id"]]]["operator_user_id"], po["po_id"], tc, "INFO",
                                  f"Inbound {ctype.lower()} update for {l['po_line_id']} via {change_id}", change_id)
                    s["last"] = prop
                    s["status"] = cr["status"]
                    if cr["status"] in ("APPROVED", "AUTO_APPROVED"):
                        s["force"] = prop
                    crs.append(cr); crs_by_line[l["po_line_id"]].append(cr); crs_of_po[po["po_id"]].append(cr)
    cr_by_id = {c["change_id"]: c for c in crs}

    # attach impact ids
    for k, im in enumerate(impacts, 1):
        im["impact_id"] = f"IMP-{k:06d}"

    # ---- inventory plan versions (approved changes only) -----------------------------------
    plan = {}
    def mk_event(l, po, ver, etype, src, qty, dt, eff):
        return dict(po_line_id=l["po_line_id"], item_id=l["item_id"], warehouse_id=po["warehouse_id"], version_no=ver, event_type=etype,
                    source_change_id=src, projected_qty=qty, projected_date=dt, effective_from=eff, effective_to=None)
    for po in pos:
        for l in lines_of_po[po["po_id"]]:
            ev = [mk_event(l, po, 1, "INITIAL", None, l["ordered_qty"], l["requested_date"], po["sent_at"])]
            apps = sorted([c for c in crs_by_line.get(l["po_line_id"], []) if c["status"] in ("APPROVED", "AUTO_APPROVED") and c["change_type"] in ("DATE", "QTY")],
                          key=lambda c: (c["closed_at"], c["revision_no"], c["change_id"]))
            for c in apps:
                t = max(c["closed_at"], ev[-1]["effective_from"] + timedelta(seconds=1))
                ev[-1]["effective_to"] = t
                ne = dict(ev[-1]); ne.update(version_no=ev[-1]["version_no"] + 1, event_type="CHANGE_APPLIED", source_change_id=c["change_id"],
                                              effective_from=t, effective_to=None)
                if c["change_type"] == "DATE":
                    ne["projected_date"] = c["_prop"]
                else:
                    ne["projected_qty"] = c["_prop"]
                ev.append(ne)
            plan[l["po_line_id"]] = ev
    baseline_final = {k: (v[-1]["projected_date"], v[-1]["projected_qty"]) for k, v in plan.items()}

    # ---- inject plan anomalies --------------------------------------------------------------
    used_lines = set()
    n_un = max(2, round(RATE["unapproved"] * n_po))
    n_st = max(2, round(RATE["stale_overwrite"] * n_po))
    cands = [c for c in crs if c["status"] in ("PENDING_APPROVAL", "REJECTED") and c["required_level"] in ("PLANNER", "MANAGER")
             and c["change_type"] in ("DATE", "QTY")]
    cands.sort(key=lambda c: c["change_id"])
    rng.shuffle(cands)
    done = 0
    for c in cands:
        if done >= n_un:
            break
        lid = c["po_line_id"]
        if lid in used_lines:
            continue
        ev = plan[lid]
        t = (c["closed_at"] + timedelta(minutes=rng.randint(5, 180))) if c["closed_at"] else (c["created_at"] + timedelta(hours=rng.randint(1, 6)))
        cur = ev[-1]["projected_date"] if c["change_type"] == "DATE" else ev[-1]["projected_qty"]
        if t > AS_OF or t <= ev[-1]["effective_from"] or cur == c["_prop"]:
            continue
        ev[-1]["effective_to"] = t
        ne = dict(ev[-1]); ne.update(version_no=ev[-1]["version_no"] + 1, event_type="CHANGE_APPLIED", source_change_id=c["change_id"], effective_from=t, effective_to=None)
        if c["change_type"] == "DATE":
            ne["projected_date"] = c["_prop"]
        else:
            ne["projected_qty"] = c["_prop"]
        ev.append(ne); used_lines.add(lid); done += 1
        gt.append(dict(issue_type="UNAPPROVED_CHANGE_UPDATES_INVENTORY_PLAN", entity="InventoryPlan", key=ne, related=c["change_id"], po_id=c["po_id"],
                       rule="plan.source_change.status NOT IN (APPROVED, AUTO_APPROVED)", decision="BLOCK_PLAN_UPDATE",
                       notes=f"Change final status = {c['status']}; plan nevertheless updated."))
    stale_c = []
    for lid in sorted(plan):
        if lid in used_lines:
            continue
        for ctype in ("DATE", "QTY"):
            applied = [e for e in plan[lid] if e["source_change_id"] and cr_by_id[e["source_change_id"]]["change_type"] == ctype]
            if len(applied) >= 2:
                newer = cr_by_id[applied[-1]["source_change_id"]]
                for e in applied[:-1]:
                    older = cr_by_id[e["source_change_id"]]
                    if older["revision_no"] < newer["revision_no"] and older["_prop"] != newer["_prop"]:
                        stale_c.append((lid, ctype, older, newer))
                        break
    rng.shuffle(stale_c)
    done = 0
    for lid, ctype, older, newer in stale_c:
        if done >= n_st:
            break
        if lid in used_lines:
            continue
        ev = plan[lid]
        t = ev[-1]["effective_from"] + timedelta(hours=rng.randint(1, 12))
        if t > AS_OF:
            continue
        ev[-1]["effective_to"] = t
        ne = dict(ev[-1]); ne.update(version_no=ev[-1]["version_no"] + 1, event_type="CHANGE_APPLIED", source_change_id=older["change_id"], effective_from=t, effective_to=None)
        if ctype == "DATE":
            ne["projected_date"] = older["_prop"]
        else:
            ne["projected_qty"] = older["_prop"]
        ev.append(ne); used_lines.add(lid); done += 1
        gt.append(dict(issue_type="OLDER_REVISION_OVERWRITES_NEWER", entity="InventoryPlan", key=ne, related=f"{older['change_id']}|{newer['change_id']}",
                       po_id=older["po_id"], rule="plan.source_change.revision_no < max revision already applied to same line/change_type",
                       decision="REJECT_STALE_REVISION", notes=f"Revision {older['revision_no']} re-applied after revision {newer['revision_no']}."))
    # assign plan ids chronologically
    all_ev = [e for lid in plan for e in plan[lid]]
    all_ev.sort(key=lambda e: (e["effective_from"], e["po_line_id"], e["version_no"]))
    for k, e in enumerate(all_ev, 1):
        e["plan_event_id"] = f"PLN-2026-{k:06d}"
        e["is_current"] = 1 if e["effective_to"] is None else 0

    # ---- production order schedule status (from baseline approved-only plan) ---------------
    for p in prods:
        bad = False
        for lk in p["_links"]:
            bd, bq = baseline_final[lk["po_line_id"]]
            lks = links_by_line[lk["po_line_id"]]
            cum = 0
            for x in lks:
                cum += x["required_qty"]
                if x is lk:
                    break
            if bd > lk["required_date"] or cum > bq:
                bad = True
        started = p["planned_start_date"] <= AS_OF.date()
        p["schedule_status"] = ("DELAYED" if started else "AT_RISK") if bad else ("RELEASED" if started else "ON_TRACK")

    # ---- PO status history, PO/line current status ------------------------------------------
    MAP = {"ACCEPTED": "CONFIRMED", "ACCEPTED_WITH_CHANGES": "CONFIRMED_WITH_CHANGES", "PARTIALLY_ACCEPTED": "PARTIALLY_CONFIRMED", "REJECTED": "SUPPLIER_REJECTED"}
    def po_state(t, po, acks_p, crs_p):
        a = [x for x in acks_p if x["ack_received_at"] <= t]
        if not a:
            return "NO_RESPONSE" if t >= po["ack_due_at"] else "SENT"
        for c in crs_p:
            if c["_needs_human"] and c["created_at"] <= t and (c["closed_at"] is None or c["closed_at"] > t):
                return "CHANGE_PENDING_APPROVAL"
        return MAP[a[-1]["ack_status"]]
    hist = []
    for po in pos:
        acks_p, crs_p = acks_of_po.get(po["po_id"], []), crs_of_po.get(po["po_id"], [])
        evs = [(po["sent_at"], 0, "PO_SENT", None)]
        if po["ack_due_at"] <= AS_OF:
            evs.append((po["ack_due_at"], 1, "SLA_BREACH", None))
            if not any(a["ack_received_at"] <= po["ack_due_at"] for a in acks_p):
                notif("SUPPLIER_SILENCE", po["planner_id"], po["po_id"], po["ack_due_at"], "WARNING", "No supplier acknowledgement by SLA due time")
        for a in acks_p:
            evs.append((a["ack_received_at"], 2, "ACK_RECEIVED", a["ack_id"]))
        for c in crs_p:
            if c["_needs_human"]:
                evs.append((c["created_at"], 3, "CHANGE_CREATED", c["change_id"]))
                if c["closed_at"] is not None:
                    evs.append((c["closed_at"], 4, "CHANGE_DECIDED", c["change_id"]))
        evs.sort(key=lambda e: (e[0], e[1], e[3] or ""))
        prev = None
        for t, _, tt, tid in evs:
            s = po_state(t, po, acks_p, crs_p)
            if s != prev:
                hist.append(dict(po_id=po["po_id"], from_status=prev, to_status=s, event_time=t, trigger_type=tt, trigger_id=tid))
                prev = s
        po["current_status"] = po_state(AS_OF, po, acks_p, crs_p)
        if prev != po["current_status"]:
            hist.append(dict(po_id=po["po_id"], from_status=prev, to_status=po["current_status"], event_time=AS_OF, trigger_type="SLA_BREACH", trigger_id=None))
        # line status
        latest = {p["po_line_id"]: p for p in promises_of_ack[acks_p[-1]["ack_id"]] if not p.get("_wrong")} if acks_p else {}
        pend = {c["po_line_id"] for c in crs_p if c["status"] == "PENDING_APPROVAL"}
        for l in lines_of_po[po["po_id"]]:
            if not acks_p:
                l["line_status_current"] = "UNCONFIRMED"
            elif l["po_line_id"] in pend:
                l["line_status_current"] = "CHANGE_PENDING"
            else:
                l["line_status_current"] = {"ACCEPTED": "CONFIRMED", "PARTIALLY_ACCEPTED": "PARTIALLY_CONFIRMED", "REJECTED": "REJECTED"}[latest[l["po_line_id"]]["line_ack_status"]]
    hist.sort(key=lambda h: (h["po_id"], h["event_time"]))
    for k, h in enumerate(hist, 1):
        h["po_status_event_id"] = f"PSE-{k:06d}"

    # ---- finalize rows ----------------------------------------------------------------------
    notifs.sort(key=lambda n: (n["sent_at"], n["notification_type"], n["po_id"], n["change_id"] or "", n["recipient_user_id"], n["prod_order_id"] or ""))
    for k, n in enumerate(notifs, 1):
        n["notification_id"] = f"NOT-2026-{k:06d}"
    T["Supplier"] = suppliers
    T["PurchaseOrder"] = pos
    T["POLine"] = lines
    T["Acknowledgement"] = sorted(acks, key=lambda a: (a["po_id"], a["revision_no"]))
    T["PromiseDate"] = sorted(promises, key=lambda p: p["promise_id"])
    T["ChangeRequest"] = sorted(crs, key=lambda c: c["change_id"])
    T["Approval"] = sorted(approvals, key=lambda a: a["approval_id"])
    T["InventoryPlan"] = all_ev
    T["ProductionOrder"] = prods
    T["ProductionOrderSupply"] = links
    T["ChangeImpact"] = impacts
    T["Notification"] = notifs
    T["POStatusHistory"] = hist
    # ground truth
    gt_rows = []
    gt.sort(key=lambda g: (g["issue_type"], g["key"].get("plan_event_id") or g["key"].get("promise_id")))
    for k, g in enumerate(gt, 1):
        rid = g["key"].get("plan_event_id") or g["key"].get("promise_id")
        gt_rows.append(dict(ground_truth_id=f"GT-{k:05d}", issue_type=g["issue_type"], entity=g["entity"], record_id=rid, po_id=g["po_id"],
                            related_record_ids=g["related"], detection_rule=g["rule"], expected_decision=g["decision"], notes=g["notes"]))
    return T, gt_rows


# ----------------------------------------------------------------------------------------------
def fmt(v, typ):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if typ == "decimal2":
        return f"{v:.2f}"
    if typ == "decimal4":
        return f"{v:.4f}"
    if typ == "bool":
        return str(int(v))
    return str(v)


def write_all(T, gt_rows, out, seed, scale, cmd):
    os.makedirs(out, exist_ok=True)
    files = {}
    for name, tdef in S.TABLES.items():
        cols = [fd["field"] for fd in tdef["fields"]]
        types = {fd["field"]: fd["type"] for fd in tdef["fields"]}
        path = os.path.join(out, f"{name}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for r in T[name]:
                w.writerow([fmt(r.get(c), types[c]) for c in cols])
        files[f"{name}.csv"] = len(T[name])
    gcols = ["ground_truth_id", "issue_type", "entity", "record_id", "po_id", "related_record_ids", "detection_rule", "expected_decision", "notes"]
    with open(os.path.join(out, "ground_truth.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(gcols)
        for r in gt_rows:
            w.writerow([r[c] for c in gcols])
    with open(os.path.join(out, "ground_truth.json"), "w", encoding="utf-8") as fh:
        json.dump(gt_rows, fh, indent=1)
    files["ground_truth.csv"] = len(gt_rows)
    with open(os.path.join(out, "schema.sql"), "w") as fh:
        fh.write(S.ddl())
    with open(os.path.join(out, "data_dictionary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["table", "field", "type", "required", "allowed_values", "unit", "uniqueness", "validation_rule", "foreign_key", "table_description", "cardinality"])
        for name, tdef in S.TABLES.items():
            for fd in tdef["fields"]:
                w.writerow([name, fd["field"], fd["type"], fd["required"], fd["allowed"].replace(",", "|"), fd["unit"], fd["uniqueness"], fd["rule"], fd["fk"],
                            tdef["desc"], tdef["cardinality"]])
    # checksums
    sums = {}
    for fn in sorted(os.listdir(out)):
        if fn in ("checksums.json", "source_manifest.json"):
            continue
        with open(os.path.join(out, fn), "rb") as fh:
            sums[fn] = hashlib.sha256(fh.read()).hexdigest()
    manifest = dict(generator="generate_data.py", version=GEN_VERSION, command=cmd, seed=seed, scale=scale, as_of=AS_OF.isoformat(),
                    external_data_used=False, sources=[], licensing="No external or personal data. All values synthetic; names/countries drawn from small hard-coded lists. Public domain reference ideas (ERP PO/ASN schemas) used for schema inspiration only.",
                    row_counts=files)
    with open(os.path.join(out, "source_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    with open(os.path.join(out, "checksums.json"), "w") as fh:
        json.dump(sums, fh, indent=1)
    return files


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--scale", type=float, default=1.0, help="1.0 = 10,000 POs / 15,000 acknowledgement revisions")
    ap.add_argument("--out", default="data_full")
    a = ap.parse_args()
    T, gt_rows = generate(a.seed, a.scale)
    counts = write_all(T, gt_rows, a.out, a.seed, a.scale, f"python generate_data.py --seed {a.seed} --scale {a.scale} --out {a.out}")
    for k, v in counts.items():
        print(f"{k:28s}{v:>9,}")
