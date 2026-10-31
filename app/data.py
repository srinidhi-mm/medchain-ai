"""Fixed, curated Indian pharma synthetic dataset, loaded from datasets/*.csv. No randomness.
The as-of date is a constant, so the same scenario + budget + horizon always gives the same state.
Scenarios are data too: datasets/scenario_overrides.csv lists the exact changes each scenario applies."""
import copy, csv, os
from datetime import date, timedelta
from statistics import mean

AS_OF = date(2026, 11, 1)
LOOKBACK = 12                       # weeks of demand history the Demand agent works from
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS = os.path.join(ROOT, "datasets")

def d(n): return (AS_OF + timedelta(days=n)).isoformat()
def off(iso): return (date.fromisoformat(iso) - AS_OF).days          # ISO date -> day offset from AS_OF
def rows(name):
    with open(os.path.join(DATASETS, name), encoding="utf-8", newline="") as f: return list(csv.DictReader(f))

def _load():
    med = {r["medicine_id"]: dict(name=r["name"], api=r["api_id"], kg_per_k=float(r["kg_api_per_1000_tablets"]), fg_stock=float(r["finished_stock_k_tablets"]),
                                  schedule=r["schedule"], pack=r["pack"], mrp=float(r["mrp_inr_per_strip"])) for r in rows("medicines.csv")}
    for m in med.values():
        for k in ("kg_per_k", "fg_stock"): m[k] = int(m[k]) if m[k] == int(m[k]) else m[k]
    apis = {r["api_id"]: r["name"] for r in rows("apis.csv")}
    sup = {r["supplier_id"]: dict(name=r["name"], city=r["city"], state=r["state"], email=r["email"], rej=float(r["rejection_rate"]), audit=r["qualification"],
                                  last_audit=r["last_audit_date"], hist=[], apis={}) for r in rows("suppliers.csv")}
    for r in rows("supplier_apis.csv"):
        sup[r["supplier_id"]]["apis"][r["api_id"]] = dict(price=int(r["price_inr_per_kg"]), cap=int(r["capacity_kg"]), moq=int(r["moq_kg"]), lead=int(r["lead_days"]))
    for r in sorted(rows("supplier_history.csv"), key=lambda r: (r["supplier_id"], r["month"])): sup[r["supplier_id"]]["hist"].append(float(r["on_time_rate"]))
    num = lambda v: int(float(v)) if float(v) == int(float(v)) else float(v)
    lots = [dict(id=r["lot_id"], api=r["api_id"], sup=r["supplier_id"], recv=num(r["received_kg"]), mfg=off(r["mfg_date"]), exp=off(r["expiry_date"]), status=r["quality_status"],
                 storage=r["storage"], received_date=r["received_date"], qc_release_date=r["qc_release_date"], coa_ref=r["coa_ref"]) for r in rows("raw_material_lots.csv")]
    orders = [dict(id=r["order_id"], med=r["medicine_id"], status=r["status"], date=off(r["order_date"])) for r in rows("production_orders.csv")]
    batches = [dict(id=r["batch_id"], med=r["medicine_id"], order=r["order_id"], date=off(r["production_date"]), status=r["quality_status"], size_k=float(r["batch_size_k_tablets"])) for r in rows("finished_batches.csv")]
    cons = [dict(lot=r["lot_id"], order=r["order_id"], kg=num(r["kg_consumed"]), date=off(r["consumption_date"])) for r in rows("material_consumption.csv")]
    pos = [dict(id=r["po_id"], sup=r["supplier_id"], api=r["api_id"], qty=num(r["qty_kg"]), eta=off(r["eta_date"]), delay=int(r["delay_days"])) for r in rows("purchase_orders.csv")]
    dem = {}
    for r in sorted(rows("demand_weekly.csv"), key=lambda r: r["week_start"]): dem.setdefault(r["medicine_id"], []).append(float(r["demand_k_tablets"]))
    usage = {}
    for r in rows("batch_lot_usage.csv"): usage.setdefault(r["batch_id"], []).append(dict(lot=r["lot_id"], kg=num(r["kg_used"])))
    for b in batches: b["usage"] = usage.get(b["id"], [])          # batch-level lot usage; empty = only order-level data exists
    disp = {}
    for r in rows("dispatch.csv"): disp.setdefault(r["batch_id"], []).append(dict(location=r["location"], city=r["city"], units_k=float(r["units_k"]), date=r["dispatch_date"], status=r["status"]))
    for b in batches: b["dispatch"] = disp.get(b["id"], [])
    daily = {}
    for r in sorted(rows("demand_daily.csv"), key=lambda r: (r["medicine_id"], r["date"])): daily.setdefault(r["medicine_id"], []).append(float(r["units_k"]))
    return dict(medicines=med, apis=apis, suppliers=sup, lots=lots, orders=orders, batches=batches, consumption=cons, pos=pos,
                demand={k: v[-LOOKBACK:] for k, v in dem.items()}, demand_full=dem, daily=daily)

BASE = _load()
_sc = rows("scenarios.csv")
SCENARIOS = {r["scenario_id"]: (r["name"], r["description"]) for r in _sc}
OVERRIDES = rows("scenario_overrides.csv")
OVERRIDE = {}   # medicine_id -> weekly demand list, set by CSV upload

def apply_override(S, o):
    t, tid, key, val = o["change_type"], o["target_id"], o["key"], o["value"]
    if t == "demand_tail":
        v = [float(x) for x in val.split("|")]; S["demand"][tid][-len(v):] = v
    elif t == "po_delay": next(p for p in S["pos"] if p["id"] == tid)["delay"] = int(val)
    elif t == "supplier_hist_tail":
        v = [float(x) for x in val.split("|")]; h = S["suppliers"][tid]["hist"]; h[-len(v):] = v
    elif t == "daily_tail":
        v = [float(x) for x in val.split("|")]; S["daily"][tid][-len(v):] = v
        dd = S["daily"][tid]; S["demand"][tid] = [round(sum(dd[i:i + 7]), 1) for i in range(len(dd) - 7 * LOOKBACK, len(dd), 7)]
    elif t == "supplier_capacity": S["suppliers"][tid]["apis"][key]["cap"] = int(val)
    elif t == "lot_status": next(l for l in S["lots"] if l["id"] == tid)["status"] = val
    elif t == "supplier_qualification": S["suppliers"][tid]["audit"] = val
    else: raise ValueError(f"unknown scenario change type {t}")

def build(scenario="baseline", budget=None, weeks=4):
    """Deterministic scenario state. Same inputs always give the same state."""
    if scenario not in SCENARIOS: raise ValueError(f"unknown scenario '{scenario}'")
    S = copy.deepcopy({k: v for k, v in BASE.items() if k != "demand_full"})
    for k, v in OVERRIDE.items(): S["demand"][k] = list(v)[-LOOKBACK:]; S["daily"].pop(k, None)   # uploaded weekly data replaces the daily series
    for o in OVERRIDES:
        if o["scenario_id"] == scenario: apply_override(S, o)
    for s in S["suppliers"].values(): s["on_time"] = mean(s["hist"])
    S.update(scenario=scenario, budget=float(budget or 1000000), weeks=int(weeks or 4), need_by=14)
    return S

_PH = {}
for _r in rows("api_price_history_inr.csv"): _PH.setdefault((_r["supplier_id"], _r["api_id"]), []).append((_r["month"], float(_r["price_inr_per_kg"])))

def price_trend(sup, api):
    """% change of the latest monthly price vs the average of the prior 6 months (reference only; does not change scores)."""
    h = [p for _, p in sorted(_PH.get((sup, api), []))]
    return None if len(h) < 7 else round((h[-1] / mean(h[-7:-1]) - 1) * 100, 1)

def catalog():
    """Dataset inventory for the UI: file, rows, description."""
    desc = {"medicines.csv": "Finished medicines, API per 1000 tablets, stock, schedule, MRP (INR)", "apis.csv": "API master with CAS number, pharmacopoeia, shelf life",
            "suppliers.csv": "Indian API suppliers: qualification status, rejection rate, last audit", "supplier_apis.csv": "Price (INR/kg), capacity, MOQ and lead time per supplier and API",
            "supplier_history.csv": "6 months of on-time rate, inspection reject %, lots, delay per supplier", "raw_material_lots.csv": "Lot-level stock: expiry, quality status, QC release, CoA",
            "production_orders.csv": "Production orders (completed, in progress, planned)", "finished_batches.csv": "Finished medicine batches linked to orders",
            "material_consumption.csv": "Raw-material lot to production order consumption", "purchase_orders.csv": "Open API purchase orders with ETA and delay",
            "demand_weekly.csv": "26 weeks of demand per medicine (agents use the latest 12)", "demand_daily.csv": "84 days of daily demand (zero days kept) used to classify smooth vs lumpy demand",
            "batch_lot_usage.csv": "Exact kg of each lot used in each finished batch (recall scope)", "dispatch.csv": "Where each finished batch went: depots shipped and units still in stock", "api_price_history_inr.csv": "12 months of INR/kg price per supplier and API",
            "scenarios.csv": "Scenario names and descriptions", "scenario_overrides.csv": "Exact data changes each scenario applies"}
    return [dict(file=f, rows=len(rows(f)), desc=desc.get(f, "")) for f in sorted(os.listdir(DATASETS)) if f.endswith(".csv")]
