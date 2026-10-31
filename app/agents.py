"""Six agents + orchestrator. Agents are deterministic, rule-based tools that read the shared
findings dict (F) produced by upstream agents and return structured output. No LLM is used;
all numbers come from exact calculations."""
import math, threading, time
from statistics import mean, pstdev
from .data import d, price_trend

ORDER = ["demand", "material", "expiry", "trace", "recovery", "guard"]
LABEL = {"demand": "Demand Forecasting", "material": "Material Risk", "expiry": "Expiry & Inventory",
         "trace": "Production & Traceability", "recovery": "Recovery Planning", "guard": "Quality Guard"}
TASK = {"demand": "Forecast demand, detect spikes, size replenishment",
        "material": "Check API availability, supplier risk, rank alternative suppliers",
        "expiry": "Check lots, expiry, quality status; compute FEFO allocation",
        "trace": "Trace rejected/risky lots to orders and finished batches; estimate production impact",
        "recovery": "Combine findings and compare budget-aware recovery plans",
        "guard": "Validate plan against quality, expiry, supplier and budget constraints"}
DEPS = {"demand": [], "material": ["demand"], "expiry": ["demand", "material"], "trace": ["material", "expiry"],
        "recovery": ["demand", "material", "expiry", "trace"], "guard": ["recovery"]}
inr = lambda v: "Rs {:,.0f}".format(v)

# ---- supplier quality grade (guides ranking and incoming-inspection intensity; it never replaces inspection or QC release)
AUDIT_PTS = {"Approved": 100, "Conditional": 60, "Suspended": 0}
INSPECT = {"A": "Standard sampling", "B": "Standard sampling", "C": "Enhanced sampling", "D": "Full testing of every container"}
def supplier_grade(s):
    qual = max(0, 100 - s["rej"] * 1000 - (10 if s["audit"] == "Conditional" else 0))
    score = round(.5 * qual + .3 * 100 * s["on_time"] + .2 * AUDIT_PTS.get(s["audit"], 0), 1)
    g = "D" if s["audit"] == "Suspended" else "A" if score >= 88 else "B" if score >= 78 else "C" if score >= 65 else "D"
    return score, g

# ---- demand pattern tools (daily series, zero days kept)
def classify(daily):
    """Syntetos-Boylan classes from average demand interval (ADI) and squared coefficient of variation (CV2) of non-zero sizes."""
    nz = [v for v in daily if v > 0]
    if not nz: return "none", None, None
    adi = len(daily) / len(nz); mu = mean(nz); cv2 = (pstdev(nz) / mu) ** 2 if mu else 0
    cls = "smooth" if adi < 1.32 and cv2 < .49 else "erratic" if adi < 1.32 else "intermittent" if cv2 < .49 else "lumpy"
    return cls, round(adi, 2), round(cv2, 2)

def sba(daily, alpha=.1):
    """Syntetos-Boylan Approximation of Croston's method: smoothed burst size / smoothed gap between bursts. Returns units per day."""
    z = p = None; q = 1
    for y in daily:
        if y > 0:
            if z is None: z, p = y, q
            else: z += alpha * (y - z); p += alpha * (q - p)
            q = 1
        else: q += 1
    return 0.0 if z is None else (1 - alpha / 2) * z / p

def window_sums(xs, n): return [sum(xs[i:i + n]) for i in range(len(xs) - n + 1)]
def pctl(xs, p):
    s_ = sorted(xs); return s_[min(len(s_) - 1, math.ceil(p * len(s_)) - 1)]

class Run:
    def __init__(s, S, on_notify=None):
        s.S, s.id, s.on_notify = S, None, on_notify
        s.events, s.findings, s.notes, s.seq, s.status, s.error = [], {}, [], 0, "created", None
        s.agents = {k: dict(status="idle", task=TASK[k], progress=0, summary=[], input=None, output=None, error=None) for k in ORDER}
        s.lock = threading.Lock()
    def ev(s, type, agent, text, data=None):
        with s.lock:
            s.seq += 1
            s.events.append(dict(seq=s.seq, t=time.strftime("%H:%M:%S"), type=type, agent=agent, text=text, data=data))
    def set(s, k, status, **kw):
        s.agents[k].update(status=status, **kw); s.ev("status", k, f"{LABEL.get(k,k)}: {status}")
    def log(s, k, text, pct=None):
        if pct is not None: s.agents[k]["progress"] = pct
        s.ev("progress", k, text, {"pct": pct})
    def message(s, frm, to, topic, payload):
        s.ev("message", frm, f"{LABEL.get(frm,frm)} -> {LABEL.get(to,to)}: {topic}", {"to": to, "payload": payload})
    def notify(s, sev, kind, msg, entity=None):
        n = dict(sev=sev, kind=kind, msg=msg, entity=entity); s.notes.append(n)
        if s.on_notify: s.on_notify(n)

# ---------------------------------------------------------------- shared helpers
def enrich_lots(S):
    used = {}
    for c in S["consumption"]: used[c["lot"]] = used.get(c["lot"], 0) + c["kg"]
    out = []
    for l in S["lots"]:
        rem = round(l["recv"] - used.get(l["id"], 0), 2)
        price = S["suppliers"][l["sup"]]["apis"].get(l["api"], {}).get("price", 0)
        es = "Expired" if l["exp"] < 0 else "Near expiry" if l["exp"] <= 60 else "OK"
        hold = l["status"] == "Released" and S["suppliers"][l["sup"]]["audit"] == "Suspended"      # supplier suspended: hold for QA review
        out.append({**l, "remaining": rem, "price": price, "days": l["exp"], "exp_date": d(l["exp"]), "mfg_date": d(l["mfg"]), "hold": hold,
                    "expiry_status": es, "usable": l["status"] == "Released" and l["exp"] >= 0 and rem > 0 and not hold, "value": round(rem * price)})
    return out

def exclusion_reason(l):
    if l["status"] == "Rejected": return "Rejected by QC"
    if l["status"] == "Quarantine": return "Quarantine: awaiting incoming inspection / QC release"
    if l["exp"] < 0: return f"Expired {-l['exp']} days ago"
    if l.get("hold"): return "Supplier suspended: lot held for QA review before any use"
    return "No remaining quantity"

def rank_suppliers(S, api, qty, budget):
    W = dict(price=.25, reliability=.20, quality=.20, lead=.15, capacity=.10, budget=.10)
    cands = [(i, s) for i, s in S["suppliers"].items() if api in s["apis"]]
    pmin = min(s["apis"][api]["price"] for _, s in cands); out = []
    for sid, s in cands:
        a = s["apis"][api]; moq = a["moq"]
        want = math.ceil(max(qty, moq) / moq) * moq
        q = min(want, a["cap"]); covered = min(qty, q); cost = q * a["price"]
        delay = max([p["delay"] for p in S["pos"] if p["sup"] == sid] + [0]); lead = a["lead"] + delay
        comp = dict(price=100 * pmin / a["price"], reliability=100 * s["on_time"],
                    quality=max(0, 100 - s["rej"] * 1000 - (10 if s["audit"] == "Conditional" else 0)),
                    lead=max(0, 100 - lead * 5), capacity=100 * min(1, a["cap"] / qty if qty else 1),
                    budget=100 * min(1, budget / cost) if cost else 100)
        eligible = s["audit"] != "Suspended"; total = round(sum(W[k] * v for k, v in comp.items()), 1) if eligible else 0
        gscore, grade = supplier_grade(s); uplift = round((a["price"] / pmin - 1) * 100)
        reasons = [f"Price Rs {a['price']:,}/kg ({'lowest' if uplift == 0 else f'+{uplift}% vs lowest'})",
                   f"Capacity {a['cap']} kg covers {covered / qty:.0%} of the {qty:.1f} kg need" if qty else "No quantity needed",
                   f"Order cost {inr(cost)} " + ("fits" if cost <= budget else "EXCEEDS") + f" remaining budget {inr(budget)}",
                   (lambda t: f"Price trend {t:+.1f}% vs prior 6-month average (reference only, not scored)" if t is not None else "Price trend: no history")(price_trend(sid, api)),
                   f"Lead time {lead} days" + (f" (includes {delay} days of open PO delay)" if delay else ""),
                   f"History: on-time {s['on_time']:.0%}, rejection {s['rej']:.1%}. Risk weighting only; incoming inspection and QC release remain mandatory",
                   f"Qualification: {s['audit']}" + ("; not eligible" if not eligible else ""),
                   f"Quality grade {grade} ({gscore}): incoming inspection level = {INSPECT[grade]}. The grade guides ranking and sampling only; it never replaces inspection or QC release"]
        out.append(dict(sup=sid, name=s["name"], city=s["city"], email=s["email"], price=a["price"], qty_order=q, covered_kg=round(covered, 1),
                        coverage=round(covered / qty, 3) if qty else 1, cost=round(cost), lead=lead, cap=a["cap"], moq=moq, on_time=round(s["on_time"], 3),
                        rej=s["rej"], audit=s["audit"], grade=grade, grade_score=gscore, inspection=INSPECT[grade], within_budget=cost <= budget, eligible=eligible, total=total,
                        comp={k: round(v, 1) for k, v in comp.items()}, weights=W, reasons=reasons))
    return sorted(out, key=lambda r: (-r["eligible"], -r["total"]))

def lots_for_order(S, oid): return [c for c in S["consumption"] if c["order"] == oid]
def forward(S, lot):
    orders = sorted({c["order"] for c in S["consumption"] if c["lot"] == lot})
    return orders, [b for b in S["batches"] if b["order"] in orders]

def lot_exposure(S, lot):
    """Exact recall scope for one lot. Batch-level usage records give exact batches; batches of an order with no
    batch-level record fall back to order level (flagged), and orders in progress have no batch yet."""
    out = []
    for c in S["consumption"]:
        if c["lot"] != lot: continue
        ob = [b for b in S["batches"] if b["order"] == c["order"]]
        exact = [b for b in ob if any(u["lot"] == lot for u in b["usage"])]
        fallback = [b for b in ob if not b["usage"]]
        out.append(dict(order=c["order"], kg=c["kg"], exact=exact, fallback=fallback, order_level=ob))
    return out

def dispatch_summary(b):
    ship = [x for x in b["dispatch"] if x["status"] == "Shipped"]; stock = [x for x in b["dispatch"] if x["status"] != "Shipped"]
    return dict(batch=b["id"], med=b["med"], in_stock_k=round(sum(x["units_k"] for x in stock), 1), shipped_k=round(sum(x["units_k"] for x in ship), 1),
                locations=[dict(location=x["location"], city=x["city"], units_k=x["units_k"]) for x in ship])

def search(S, q):
    q = (q or "").strip().upper(); lots = {l["id"]: l for l in enrich_lots(S)}; nodes, edges = {}, []
    def sup(sid): nodes[sid] = dict(id=sid, type="supplier", col=0, label=sid, sub=S["suppliers"][sid]["name"], status=S["suppliers"][sid]["audit"])
    def lot(l): nodes[l["id"]] = dict(id=l["id"], type="lot", col=1, label=l["id"], sub=f"{l['remaining']} kg left", status=l["status"]); sup(l["sup"]); edges.append([l["sup"], l["id"], "supplied"])
    def order(oid): o = next(o for o in S["orders"] if o["id"] == oid); nodes[oid] = dict(id=oid, type="order", col=2, label=oid, sub=o["status"], status=o["status"])
    def batch(b, status=None, sub=None):
        ds = dispatch_summary(b); nodes[b["id"]] = dict(id=b["id"], type="batch", col=3, label=b["id"], sub=sub or f"{ds['in_stock_k']}k in stock, {ds['shipped_k']}k shipped", status=status or b["status"])
    batches = {b["id"]: b for b in S["batches"]}
    if q in lots:
        lot(lots[q]); bad = lots[q]["status"] == "Rejected" or lots[q]["hold"]
        for e in lot_exposure(S, q):
            order(e["order"]); edges.append([q, e["order"], f"{e['kg']} kg"])
            for b in e["exact"]:
                u = next(u["kg"] for u in b["usage"] if u["lot"] == q); batch(b, "Exposed" if bad else None); edges.append([e["order"], b["id"], f"{u} kg in batch"])
            for b in e["fallback"]:
                batch(b, "Exposed" if bad else None, "order-level only: no batch record"); edges.append([e["order"], b["id"], "order-level"])
        kind = "lot"
    elif q in batches:
        b = batches[q]; batch(b); order(b["order"]); edges.append([b["order"], q, "produced"])
        used = b["usage"] or [dict(lot=c["lot"], kg=c["kg"]) for c in lots_for_order(S, b["order"])]
        for u in used: lot(lots[u["lot"]]); edges.append([u["lot"], b["order"], f"{u['kg']} kg" + ("" if b["usage"] else " (order-level)")])
        kind = "batch"
    else: return dict(found=False, q=q)
    return dict(found=True, q=q, kind=kind, nodes=list(nodes.values()), edges=edges)

# ---------------------------------------------------------------- agents
def lumpy_item(S, mid, m, daily, cls, adi, cv2, lead, h, W):
    """Burst-aware forecast for intermittent / lumpy medicines: SBA rate + safety stock from the P95 of lead-time demand."""
    stock, kg = m["fg_stock"], m["kg_per_k"]; rate = sba(daily); lvl = rate * 7
    ws = window_sums(daily, lead); mean_ws, p95 = mean(ws), pctl(ws, .95); safety = max(0.0, p95 - mean_ws)
    fc = lvl * W; band = 1.28 * (pstdev(h) if len(h) > 1 else 0) * math.sqrt(W)
    prob = sum(1 for x in ws if x > stock) / len(ws); cover = stock / lvl if lvl else 99
    risk = "High" if prob >= .25 or cover < 1.5 else "Medium" if prob >= .10 or cover < 3 else "Low"
    w7 = window_sums(daily, 7); last7 = w7[-1]; p95_7 = pctl(w7[:-1], .95); z = (last7 - mean(w7)) / max(pstdev(w7), .05 * mean(w7))
    pat = "spike" if last7 > p95_7 else "normal"; need = max(0.0, fc + safety - stock); nz = sum(1 for v in daily if v > 0)
    ev = (f"{cls.capitalize()} demand: sold on {nz} of {len(daily)} days (ADI {adi}, CV2 {cv2}). SBA rate {lvl:.1f}k/wk vs naive average {mean(h):.1f}k/wk. "
          f"Demand over the {lead}-day lead time: mean {mean_ws:.0f}k but P95 {p95:.0f}k, so safety stock {safety:.0f}k. A burst exceeds stock in {prob:.0%} of {lead}-day windows. Last 7 days {last7:.0f}k vs P95 {p95_7:.0f}k")
    return dict(med=mid, name=m["name"], api=m["api"], history=h, level=round(lvl, 1), baseline=round(mean(h), 1), z=round(z, 1), pattern=pat, forecast=round(fc),
                low=round(max(0, fc - band)), high=round(fc + band), stock=stock, cover_weeks=round(cover, 1), stockout_risk=risk, replenish_k=round(need, 1),
                required_kg=round(need * kg, 1), weekly_kg=round(lvl * kg, 2), evidence=ev, demand_class=cls, adi=adi, cv2=cv2, method="SBA rate + burst safety stock",
                daily=daily, lead_days=lead, p95_leadtime=round(p95, 1), mean_leadtime=round(mean_ws, 1), safety_k=round(safety, 1), stockout_prob=round(prob, 2),
                naive_forecast=round(mean(h) * W), selling_days=nz, last7=round(last7, 1), p95_week=round(p95_7, 1))

def demand(S, F, run):
    items = []
    for mid, m in S["medicines"].items():
        daily = S["daily"].get(mid); cls, adi, cv2 = classify(daily) if daily else ("smooth", None, None)
        lead = min([s["apis"][m["api"]]["lead"] for s in S["suppliers"].values() if m["api"] in s["apis"] and s["audit"] != "Suspended"] or [7])
        h = S["demand"][mid]; W = S["weeks"]
        if cls in ("intermittent", "lumpy"): it = lumpy_item(S, mid, m, daily, cls, adi, cv2, lead, h, W)
        else:
            base = h[:-3]; mu = mean(base); sd = max(pstdev(base), .05 * mu)
            lvl = .5 * h[-1] + .3 * h[-2] + .2 * h[-3]; z = (lvl - mu) / sd
            pat = "spike" if z > 2 else "drop" if z < -2 else "normal"
            fc = lvl * W; band = 1.28 * sd * math.sqrt(W)
            cover = m["fg_stock"] / lvl if lvl else 99; need = max(0, fc + lvl - m["fg_stock"])
            risk = "High" if cover < 1.5 else "Medium" if cover < 3 else "Low"
            it = dict(med=mid, name=m["name"], api=m["api"], history=h, level=round(lvl, 1), baseline=round(mu, 1), z=round(z, 1), pattern=pat,
                      forecast=round(fc), low=round(fc - band), high=round(fc + band), stock=m["fg_stock"], cover_weeks=round(cover, 1),
                      stockout_risk=risk, replenish_k=round(need, 1), required_kg=round(need * m["kg_per_k"], 1), weekly_kg=round(lvl * m["kg_per_k"], 2),
                      evidence=f"Weighted level {lvl:.1f}k/wk vs {len(base)}-week baseline {mu:.1f}k (z={z:.1f}); cover {cover:.1f} weeks",
                      demand_class=cls, adi=adi, cv2=cv2, method="Weighted level (last 3 weeks)", daily=daily or [], lead_days=lead)
        items.append(it)
        run.log("demand", f"{it['name']}: {it['demand_class']} demand, level {it['level']}k/wk, pattern={it['pattern']}, stockout risk {it['stockout_risk']} [{it['method']}]", 30 + 15 * len(items))
        if it["pattern"] == "spike":
            msg = (f"Demand burst on {it['name']}: {it['last7']:.0f}k in 7 days vs usual peak {it['p95_week']:.0f}k" if it["demand_class"] in ("intermittent", "lumpy")
                   else f"Demand spike on {it['name']}: {it['level']:.0f}k/wk vs baseline {it['baseline']:.0f}k")
            run.notify("critical", "demand_spike", msg, mid)
        elif it["stockout_risk"] == "High": run.notify("warning", "stockout_risk", f"High stockout risk on {it['name']} ({it['cover_weeks']:.1f} weeks cover)", mid)
    flagged = [i for i in items if i["pattern"] != "normal" or i["stockout_risk"] == "High"]
    summ = [f"{i['name']}: {i['pattern']}, cover {i['cover_weeks']} wk, replenish {i['replenish_k']}k ({i['required_kg']} kg API)" + (f" [{i['demand_class']} demand, burst-aware]" if i["demand_class"] in ("intermittent", "lumpy") else "") for i in items]
    return dict(items=items, summary=summ, attention=bool(flagged),
                handoff=dict(spikes=[i["med"] for i in items if i["pattern"] == "spike"], classes={i["med"]: i["demand_class"] for i in items}, required_kg={i["api"]: i["required_kg"] for i in items}))

def material(S, F, run):
    lots = enrich_lots(S); items = F["demand"]["items"]; sups = []
    for sid, s in S["suppliers"].items():
        delay = max([p["delay"] for p in S["pos"] if p["sup"] == sid] + [0])
        risk = 100 * (.45 * min((1 - s["on_time"]) / .3, 1) + .25 * min(s["rej"] / .06, 1) + .30 * min(delay / 14, 1))
        risk = min(100, round(risk + {"Conditional": 10, "Suspended": 100}.get(s["audit"], 0)))
        gscore, grade = supplier_grade(s)
        sups.append(dict(id=sid, name=s["name"], city=s["city"], on_time=round(s["on_time"], 3), rej=s["rej"], delay_days=delay, audit=s["audit"], grade=grade, grade_score=gscore, inspection=INSPECT[grade],
                         risk=risk, level="High" if risk >= 55 else "Medium" if risk >= 30 else "Low", hist=s["hist"]))
    run.log("material", f"Scored {len(sups)} suppliers on on-time history, rejection rate, open PO delay, qualification", 35)
    ok_sup = {sid for sid, s in S["suppliers"].items() if s["audit"] != "Suspended"}
    rows, short, delayed = [], [], [p for p in S["pos"] if p["delay"] > 0]
    for it in items:
        api = it["api"]; usable = sum(l["remaining"] for l in lots if l["api"] == api and l["usable"])
        inbound = sum(p["qty"] for p in S["pos"] if p["api"] == api and p["sup"] in ok_sup and p["eta"] + p["delay"] <= S["need_by"])
        late = sum(p["qty"] for p in S["pos"] if p["api"] == api and (p["delay"] > 0 or p["sup"] not in ok_sup))
        gap = round(max(0, it["required_kg"] - usable - inbound), 1)
        row = dict(api=api, api_name=S["apis"][api], med=it["med"], required=it["required_kg"], usable=round(usable, 1), inbound=inbound, delayed_or_excluded_inbound=late, shortfall=gap)
        rows.append(row)
        run.log("material", f"{api}: need {it['required_kg']} kg, usable {usable:.1f}, inbound in {S['need_by']}d {inbound}, shortfall {gap}", 60)
        if gap > 0:
            row["value_at_risk"] = round(gap * min(s["apis"][api]["price"] for s in S["suppliers"].values() if api in s["apis"])); short.append(row)
            run.notify("critical", "material_shortage", f"{S['apis'][api]} shortfall {gap} kg for {it['name']}", api)
    for p in delayed:
        run.notify("critical" if any(r["api"] == p["api"] for r in short) else "warning", "supplier_delay",
                   f"{p['id']} from {S['suppliers'][p['sup']]['name']} delayed {p['delay']} days ({p['qty']} kg)", p["id"])
    ranking = {r["api"]: rank_suppliers(S, r["api"], r["shortfall"], S["budget"]) for r in short}
    for api, rk in ranking.items(): run.log("material", f"{api}: top supplier {rk[0]['sup']} (score {rk[0]['total']})", 85)
    summ = [f"{r['api']}: need {r['required']} kg, available {r['usable'] + r['inbound']:.1f} kg, shortfall {r['shortfall']} kg" for r in rows]
    summ += [f"{p['id']} delayed {p['delay']} days" for p in delayed] + [f"Supplier {x['id']} risk {x['risk']} ({x['level']})" for x in sups if x["level"] != "Low"]
    return dict(suppliers=sups, materials=rows, shortages=short, delayed_pos=delayed, ranking=ranking, summary=summ, attention=bool(short or delayed),
                handoff=dict(shortages={r["api"]: r["shortfall"] for r in short}, delayed=[p["id"] for p in delayed]))

def expiry(S, F, run):
    lots = enrich_lots(S); req = F["demand"]["handoff"]["required_kg"]; alloc, per_lot = [], {}
    for api, need in req.items():
        for l in sorted([l for l in lots if l["api"] == api and l["usable"]], key=lambda l: l["exp"]):
            take = round(min(need, l["remaining"]), 2)
            if take > 0:
                alloc.append(dict(api=api, lot=l["id"], kg=take, exp_date=l["exp_date"], days=l["days"], sup=l["sup"])); per_lot[l["id"]] = take; need -= take
    run.log("expiry", f"FEFO allocated {len(alloc)} lot slices; lots sorted by expiry, usable status only", 55)
    excl = [dict(lot=l["id"], api=l["api"], kg=l["remaining"], reason=exclusion_reason(l)) for l in lots if not l["usable"]]
    waste, avoided, expired_val = [], 0, 0
    for l in lots:
        if l["usable"] and l["days"] <= 60:
            left = round(l["remaining"] - per_lot.get(l["id"], 0), 2)
            avoided += per_lot.get(l["id"], 0) * l["price"]
            if left > 0: waste.append(dict(lot=l["id"], kg=left, value=round(left * l["price"]), days=l["days"]))
        if l["expiry_status"] == "Expired": expired_val += l["value"]
        l["alloc_kg"] = per_lot.get(l["id"], 0)
    wk_kg = {i["api"]: i["weekly_kg"] for i in F["demand"]["items"]}; use_in_time = []
    for api in sorted({l["api"] for l in lots}):
        cum = 0.0                                          # kg already claimed by earlier-expiring lots (FEFO)
        for l in sorted([x for x in lots if x["api"] == api and x["usable"]], key=lambda x: x["exp"]):
            cap = max(0.0, wk_kg.get(api, 0) * l["days"] / 7 - cum); use = min(l["remaining"], cap); cum += use
            unused = round(l["remaining"] - use, 2); wk = wk_kg.get(api, 0); need_days = round(l["remaining"] / wk * 7) if wk else None
            l["unused_at_expiry"] = unused
            l["time_status"] = "At risk" if unused > 0 else "Tight" if need_days is not None and need_days > .7 * l["days"] else "On track"
            l["days_to_consume"] = need_days
            if l["time_status"] != "On track":
                use_in_time.append(dict(lot=l["id"], api=api, kg=l["remaining"], unused_kg=unused, value=round(unused * l["price"]), days_left=l["days"], days_to_consume=need_days, status=l["time_status"],
                    action=("Will not be used up before expiry at the current run-rate: prioritise in FEFO order, transfer to another site or return to supplier" if unused > 0
                            else "Needs most of the time left: keep first in line under FEFO")))
    held = [dict(lot=l["id"], api=l["api"], kg=l["remaining"], sup=l["sup"]) for l in lots if l["hold"] and l["remaining"] > 0]
    wv = sum(w["value"] for w in waste); near = round(sum(l["remaining"] for l in lots if l["usable"] and l["days"] <= 60), 1)
    risk = "High" if wv > 100000 else "Medium" if wv > 0 or expired_val else "Low"
    for l in lots:
        if l["usable"] and l["days"] <= 60: run.notify("warning", "near_expiry", f"{l['id']} expires in {l['days']} days ({l['remaining']} kg)", l["id"])
        if l["status"] == "Rejected": run.notify("critical", "lot_rejected", f"Lot {l['id']} is rejected; {l['remaining']} kg excluded from use", l["id"])
        if l["expiry_status"] == "Expired": run.notify("warning", "expired_lot", f"{l['id']} expired {-l['days']} days ago; excluded", l["id"])
    summ = [f"Near-expiry stock {near} kg; projected wastage {inr(wv)}; already expired value {inr(expired_val)}", f"FEFO consumption of near-expiry lots avoids {inr(avoided)}"]
    summ += [f"Excluded {e['lot']}: {e['reason']}" for e in excl]
    summ += [f"Use-in-time {u['lot']}: {u['status']}, {u['kg']} kg needs ~{u['days_to_consume']} days at run-rate, {u['days_left']} days left" for u in use_in_time]
    for u in use_in_time:
        if u["status"] == "At risk": run.notify("warning", "use_in_time", f"{u['lot']} will not be used up before expiry ({u['unused_kg']} kg, {inr(u['value'])})", u["lot"])
    for h_ in held: run.notify("warning", "supplier_hold", f"Lot {h_['lot']} held for QA review: supplier {h_['sup']} is suspended", h_["lot"])
    return dict(lots=lots, allocations=alloc, excluded=excl, wastage=waste, wastage_value=round(wv), expired_value=round(expired_val), near_qty=near,
                avoided_value=round(avoided), risk=risk, use_in_time=use_in_time, held=held, summary=summ, attention=risk != "Low" or bool(excl) or bool(use_in_time),
                handoff=dict(allocations=[(a["lot"], a["kg"]) for a in alloc], excluded=[e["lot"] for e in excl], wastage_value=round(wv)))

def trace(S, F, run):
    aff, expo, order_level, bset = [], {}, set(), {b["id"]: b for b in S["batches"]}
    for l in F["expiry"]["lots"]:
        if l["status"] != "Rejected": continue
        for e in lot_exposure(S, l["id"]):
            ids = [b["id"] for b in e["exact"]] + [b["id"] for b in e["fallback"]]; order_level |= {b["id"] for b in e["order_level"]}
            for b in e["exact"] + e["fallback"]:
                x = expo.setdefault(b["id"], dict(dispatch_summary(b), kg_from_lot=0, scope="batch-level record" if b in e["exact"] else "order-level only (no batch record)"))
                x["kg_from_lot"] += next((u["kg"] for u in b["usage"] if u["lot"] == l["id"]), 0)
            aff.append(dict(lot=l["id"], order=e["order"], kg=e["kg"], batches=ids, exact_batches=[b["id"] for b in e["exact"]], order_level_only=[b["id"] for b in e["fallback"]],
                            batch_status=[bset[i]["status"] for i in ids], state="finished batches" if ids else "in progress, no batch yet"))
    run.log("trace", f"Forward-traced rejected lots: {len(aff)} consumption records, {len(expo)} exposed batches", 50)
    meds = {S["medicines"][r["med"]]["api"]: r for r in F["material"]["shortages"]}; delayed = []
    for o in S["orders"]:
        m = S["medicines"][o["med"]]
        if o["status"] == "Planned" and m["api"] in meds:
            wk = next(i for i in F["demand"]["items"] if i["med"] == o["med"])["weekly_kg"]
            delayed.append(dict(order=o["id"], med=o["med"], date=d(o["date"]), shortfall_kg=meds[m["api"]]["shortfall"], delay_days_if_unmitigated=math.ceil(meds[m["api"]]["shortfall"] / wk * 7) if wk else 0))
    batches = sorted(expo); exposure = [expo[b] for b in batches]
    for x in exposure:
        run.notify("critical", "batches_affected", f"Finished batch {x['batch']} used a rejected lot ({x['kg_from_lot']} kg): {x['in_stock_k']}k units in stock, {x['shipped_k']}k shipped to {len(x['locations'])} location(s); QA review needed", x["batch"])
    narrowed = len(order_level) - len(batches)
    summ = ([f"{len(batches)} finished batches and {len({a['order'] for a in aff})} orders used rejected lots: {', '.join(batches) or 'none'}"]
            + ([f"Batch-level records narrow recall scope from {len(order_level)} to {len(batches)} batches ({narrowed} cleared)"] if narrowed > 0 else [])
            + [f"Units to hold: {sum(x['in_stock_k'] for x in exposure):.0f}k in stock; to recall: {sum(x['shipped_k'] for x in exposure):.0f}k shipped"] if aff else ["No rejected lots; no batch exposure"])
    summ += [f"{x['order']} at risk: ~{x['delay_days_if_unmitigated']} days delay if shortage unmitigated" for x in delayed]
    return dict(affected=aff, affected_batches=batches, exposure=exposure, scope_cleared=max(0, narrowed), delayed_orders=delayed, summary=summ, attention=bool(aff or delayed),
                handoff=dict(affected_batches=batches, delayed_orders=[x["order"] for x in delayed], hold_k=round(sum(x["in_stock_k"] for x in exposure), 1), recall_k=round(sum(x["shipped_k"] for x in exposure), 1)))

def recovery(S, F, run):
    remaining = S["budget"]; chosen, all_plans, drafts = [], {}, []
    dem = {i["api"]: i for i in F["demand"]["items"]}
    def plan(pid, label, lines, short, api):
        qty = sum(l["qty"] for l in lines); cost = sum(l["cost"] for l in lines); unc = round(max(0, short - qty), 1); wk = dem[api]["weekly_kg"]
        sc = [l["score"] for l in lines]
        return dict(id=pid, label=label, api=api, lines=lines, cost=cost, coverage=round(min(1, qty / short), 3) if short else 1, uncovered_kg=unc,
                    delay_days=math.ceil(unc / wk * 7) if wk and unc else 0, lead=max([l["lead"] for l in lines] + [0]),
                    avg_score=round(mean(sc), 1) if sc else 0, within_budget=cost <= remaining)
    line = lambda r, q: dict(sup=r["sup"], name=r["name"], email=r["email"], qty=q, price=r["price"], cost=q * r["price"], lead=r["lead"], score=r["total"], grade=r["grade"], inspection=r["inspection"])
    for sh in sorted(F["material"]["shortages"], key=lambda r: -r["value_at_risk"]):
        api, short = sh["api"], sh["shortfall"]; rk = rank_suppliers(S, api, short, remaining); el = [r for r in rk if r["eligible"]]; plans = []
        if el:
            t = el[0]; plans.append(plan("A", f"Single source: {t['name']}", [line(t, t["qty_order"])], short, api))
            if t["coverage"] < 1 and len(el) > 1:
                rem, ls = short, []
                for r in el[:2]:
                    q = min(rem, r["cap"]); q = max(q, r["moq"]); ls.append(line(r, q)); rem -= q
                    if rem <= 0: break
                plans.append(plan("B", "Dual source: " + " + ".join(l["name"] for l in ls), ls, short, api))
            if not plans[0]["within_budget"]:
                q = min(short, t["cap"], math.floor(remaining / t["price"] / t["moq"]) * t["moq"])
                if q >= t["moq"]: plans.append(plan("C", f"Budget-capped order from {t['name']} + reschedule rest", [line(t, q)], short, api))
        plans.append(plan("D", "No procurement: reschedule production", [], short, api))
        feas = [p for p in plans if p["within_budget"] and p["id"] != "D"] or [plans[-1]]
        best = max(feas, key=lambda p: (60 * p["coverage"] + .4 * p["avg_score"], -p["cost"]))
        why = [f"Plan {best['id']} covers {best['coverage']:.0%} for {inr(best['cost'])} (supplier score {best['avg_score']}, lead {best['lead']} days)"]
        for p in plans:
            if p is not best: why.append(f"Plan {p['id']} ({p['label']}): coverage {p['coverage']:.0%}, cost {inr(p['cost'])}" + ("" if p["within_budget"] else f", exceeds remaining budget by {inr(p['cost'] - remaining)}"))
        all_plans[api] = dict(plans=plans, chosen=best["id"], why=why, ranking=rk); chosen.append(best); remaining -= best["cost"]
        run.log("recovery", f"{api}: compared {len(plans)} plans; chose {best['id']} ({best['coverage']:.0%} coverage, {inr(best['cost'])})", 70)
        for l in best["lines"]:
            drafts.append(dict(supplier_id=l["sup"], to=l["email"], subject=f"Request for quotation and supply confirmation: {S['apis'][api]} ({{REC_ID}})",
                body=f"Dear {l['name']} team,\n\nWe request your quotation and availability confirmation for {l['qty']} kg of {S['apis'][api]} at approximately Rs {l['price']:,}/kg, "
                     f"required within {l['lead']} days.\n\nPlease note:\n- This is a request for quotation, not a purchase order. A purchase order will follow only after internal approval and commercial finalisation.\n"
                     f"- Material must ship with a Certificate of Analysis and will be quarantined for incoming inspection and QC release before any use. Your historical quality record does not waive this.\n"
                     f"- Incoming inspection level planned for your material: {l['inspection']} (supplier quality grade {l['grade']}).\n\n"
                     f"Regards,\nProcurement, MedChain Demo Pharma Ltd\nRef: {{REC_ID}}\n", api=api, qty=l["qty"]))
    actions, n = [], 1
    t = F["trace"]
    if t["affected_batches"]:
        ex = t["exposure"]; locs = sorted({f"{x_['location']}" for e_ in ex for x_ in e_["locations"]}); inprog = any(a["state"].startswith("in progress") for a in t["affected"])
        actions.append(dict(p=n, text=f"QA to hold {t['handoff']['hold_k']:.0f}k in-stock units and recall {t['handoff']['recall_k']:.0f}k shipped units of batches {', '.join(t['affected_batches'])}"
                                      + (f" (shipped to {', '.join(locs)})" if locs else "") + (" and review the in-progress order using the rejected lot" if inprog else ""), external=False)); n += 1
    for p in S["pos"]:
        if S["suppliers"][p["sup"]]["audit"] == "Suspended":
            actions.append(dict(p=n, text=f"Hold or cancel open {p['id']} ({p['qty']} kg) with suspended supplier {p['sup']} pending QA and procurement review; no goods to be received", external=False)); n += 1
    for h_ in F["expiry"]["held"]:
        actions.append(dict(p=n, text=f"QA to review held lot {h_['lot']} ({h_['kg']} kg) from suspended supplier {h_['sup']} before any use", external=False)); n += 1
    for c in chosen:
        if c["lines"]: actions.append(dict(p=n, text=f"Send RFQ to {', '.join(l['name'] + ' (' + str(l['qty']) + ' kg)' for l in c['lines'])} after approval", external=True)); n += 1
        if c["uncovered_kg"]: actions.append(dict(p=n, text=f"Reschedule {c['api']}-dependent production; ~{c['delay_days']} days delay on uncovered {c['uncovered_kg']} kg", external=False)); n += 1
    if F["expiry"]["allocations"]: actions.append(dict(p=n, text="Reserve usable lots in FEFO order: " + ", ".join(f"{a['lot']} ({a['kg']} kg)" for a in F['expiry']['allocations']), external=False)); n += 1
    cost = round(sum(c["cost"] for c in chosen)); covs = [c["coverage"] for c in chosen]
    summ = [f"{len(chosen)} procurement plan(s), total {inr(cost)} of {inr(S['budget'])} budget"] if chosen else ["No shortage: FEFO allocation only, no procurement"]
    summ += [c["lines"] and f"{c['api']}: Plan {c['id']} - {c['label']}" or f"{c['api']}: reschedule only" for c in chosen]
    run.notify("info", "plan_ready", f"Recovery plan ready: {len(actions)} actions, {inr(cost)}", None)
    return dict(chosen=chosen, plans=all_plans, drafts=drafts, actions=actions, total_cost=cost, budget=S["budget"], budget_used=round(cost / S["budget"], 3),
                coverage=round(min(covs), 3) if covs else 1, wastage_avoided=F["expiry"]["avoided_value"], summary=summ, attention=bool(chosen or actions),
                handoff=dict(total_cost=cost, actions=len(actions), procurement=[c["id"] for c in chosen]))

def guard(S, F, run):
    R, lots = F["recovery"], {l["id"]: l for l in F["expiry"]["lots"]}; checks, review = [], []
    bad = [a["lot"] for a in F["expiry"]["allocations"] if not (lots[a["lot"]]["status"] == "Released" and lots[a["lot"]]["days"] >= 0)]
    checks.append(dict(check="Allocated lots are released and unexpired", result="fail" if bad else "pass", detail=", ".join(bad) or f"{len(F['expiry']['allocations'])} allocation(s) verified"))
    for c in R["chosen"]:
        for l in c["lines"]:
            s = S["suppliers"][l["sup"]]
            if s["audit"] == "Suspended": checks.append(dict(check=f"Supplier {l['sup']} eligibility", result="fail", detail="Supplier suspended"))
            elif s["audit"] == "Conditional": checks.append(dict(check=f"Supplier {l['sup']} qualification", result="warn", detail="Conditionally approved: QA sign-off needed")); review.append("Supplier qualification (conditional)")
            gs_, g_ = supplier_grade(s)
            if g_ in ("C", "D"): checks.append(dict(check=f"Supplier {l['sup']} quality grade {g_}", result="warn", detail=f"Grade {g_} ({gs_}): {INSPECT[g_]} on receipt")); review.append(f"Supplier grade {g_}: {INSPECT[g_].lower()}")
            if s["rej"] > .03: checks.append(dict(check=f"Supplier {l['sup']} rejection history", result="warn", detail=f"Rejection rate {s['rej']:.1%} above 3%")); review.append("Elevated rejection history")
    checks.append(dict(check="Total within budget", result="pass" if R["total_cost"] <= R["budget"] else "warn", detail=f"{inr(R['total_cost'])} of {inr(R['budget'])}"))
    if R["total_cost"] > R["budget"]: review.append("Budget exceeded")
    unc = [c for c in R["chosen"] if c["uncovered_kg"]]
    if unc: checks.append(dict(check="Shortage fully covered", result="warn", detail=", ".join(f"{c['api']} short {c['uncovered_kg']} kg" for c in unc))); review.append("Residual shortage / production delay")
    if F["trace"]["affected_batches"]: checks.append(dict(check="Finished batch exposure", result="warn", detail=", ".join(F["trace"]["affected_batches"]))); review.append("QA batch investigation")
    if F["expiry"]["held"]: checks.append(dict(check="Lots from suspended supplier held", result="warn", detail=", ".join(h_["lot"] for h_ in F["expiry"]["held"]))); review.append("QA review of held lots")
    if any(c["lines"] for c in R["chosen"]): checks.append(dict(check="Incoming inspection", result="info", detail="All new material enters quarantine; historical supplier quality never replaces incoming inspection and QC release"))
    blocked = [dict(action=f"Use lot {e['lot']} in production", reason=e["reason"]) for e in F["expiry"]["excluded"]]
    blocked += [dict(action=f"Source from {s['id']}", reason="Supplier suspended") for s in F["material"]["suppliers"] if s["audit"] == "Suspended"]
    status = "BLOCKED" if any(c["result"] == "fail" for c in checks) else "REVIEW" if review else "PASS"
    for c in checks:
        if c["result"] == "fail": run.notify("critical", "validation_failed", f"Quality validation failed: {c['check']}", None)
    run.notify("critical" if status == "BLOCKED" else "warning", "approval_required", f"Recovery plan awaiting human approval (validation: {status})", None)
    summ = [f"Validation: {status}"] + [f"{c['check']}: {c['detail']}" for c in checks if c["result"] in ("fail", "warn")]
    return dict(status=status, checks=checks, blocked=blocked, review=sorted(set(review)), summary=summ, attention=status != "PASS",
                state="blocked" if status == "BLOCKED" else "attention" if status == "REVIEW" else "completed", handoff=dict(status=status))

FUNCS = dict(demand=demand, material=material, expiry=expiry, trace=trace, recovery=recovery, guard=guard)

def run_pipeline(run, start=0):
    run.status = "running"; run.error = None
    if start == 0:
        for k in ORDER:
            if DEPS[k]: run.set(k, "waiting", progress=0, error=None, task="Waiting for " + ", ".join(LABEL[x] for x in DEPS[k]))
    for k in ORDER[start:]:
        inp = {x: run.findings[x]["handoff"] for x in DEPS[k]} or {"scenario": run.S["scenario"], "budget": run.S["budget"], "weeks": run.S["weeks"]}
        run.message("orchestrator", k, "task_assignment", {"task": TASK[k]})
        run.set(k, "analyzing", task=TASK[k], input=inp, progress=5, error=None)
        try:
            out = FUNCS[k](run.S, run.findings, run)
        except Exception as e:
            run.set(k, "blocked", error=f"{type(e).__name__}: {e}"); run.ev("error", k, str(e)); run.status, run.error = "failed", k; return
        run.findings[k] = out
        run.set(k, out.get("state") or ("attention" if out["attention"] else "completed"), progress=100, summary=out["summary"], output=out["handoff"])
        for j in ORDER:
            if k in DEPS[j]: run.message(k, j, "findings", out["handoff"])
    run.status = "completed"

def health(F):
    s = 100 - 12 * sum(1 for i in F["demand"]["items"] if i["pattern"] == "spike") - 8 * sum(1 for i in F["demand"]["items"] if i["stockout_risk"] == "High")
    s -= 14 * len(F["material"]["shortages"]) + 8 * len(F["material"]["delayed_pos"]) + 15 * len(F["trace"]["affected_batches"] and [1]) + (10 if F["expiry"]["risk"] == "High" else 4 if F["expiry"]["risk"] == "Medium" else 0)
    return max(5, s)

def analyze(S):
    r = Run(S); run_pipeline(r); return r
