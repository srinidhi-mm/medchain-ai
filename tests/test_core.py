"""Run: python -m unittest discover -s tests   (standard library only)"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import agents, data

def run(s, b=1000000, w=4): return agents.analyze(data.build(s, b, w)).findings
def dox(F): return next(i for i in F["demand"]["items"] if i["med"] == "MED-DOX100")

class Core(unittest.TestCase):
    def test_deterministic(self):
        a, b = run("combined"), run("combined")
        self.assertEqual(a["recovery"]["total_cost"], b["recovery"]["total_cost"]); self.assertEqual(a["recovery"]["actions"], b["recovery"]["actions"])

    def test_scenarios_change_outputs(self):
        self.assertEqual(run("baseline")["recovery"]["total_cost"], 0)
        self.assertTrue(run("surge")["demand"]["handoff"]["spikes"])
        self.assertTrue(run("disruption")["material"]["delayed_pos"])
        self.assertTrue(run("expiry")["expiry"]["near_qty"] > 0)
        self.assertTrue(run("quality")["trace"]["affected_batches"])
        self.assertEqual(run("combined")["guard"]["status"], "REVIEW")
        self.assertIn("MED-DOX100", run("lumpy")["demand"]["handoff"]["spikes"])

    def test_budget_and_horizon_change_recommendation(self):
        self.assertNotEqual(run("combined", 500000)["recovery"]["total_cost"], run("combined", 1500000)["recovery"]["total_cost"])
        self.assertLessEqual(run("combined", 500000)["recovery"]["total_cost"], 500000)
        self.assertNotEqual(run("surge", w=2)["demand"]["items"][1]["forecast"], run("surge", w=6)["demand"]["items"][1]["forecast"])

    def test_never_allocates_bad_lots(self):
        for s in data.SCENARIOS:
            F = run(s); lots = {l["id"]: l for l in F["expiry"]["lots"]}
            for a in F["expiry"]["allocations"]:
                self.assertEqual(lots[a["lot"]]["status"], "Released"); self.assertGreaterEqual(lots[a["lot"]]["days"], 0); self.assertFalse(lots[a["lot"]]["hold"])
        self.assertTrue({"L-AZI-102", "L-PCM-009", "L-MET-QC"} <= {e["lot"] for e in run("quality")["expiry"]["excluded"]})

    def test_fefo_order(self):
        al = [a for a in run("baseline")["expiry"]["allocations"] if a["api"] == "API-MET"]
        self.assertEqual([a["days"] for a in al], sorted(a["days"] for a in al))

    def test_suspended_supplier(self):
        F = run("quality")
        for c in F["recovery"]["chosen"]:
            for l in c["lines"]: self.assertNotEqual(l["sup"], "S-02")
        rk = next(iter(F["material"]["ranking"].values())); self.assertFalse([r for r in rk if r["sup"] == "S-02"][0]["eligible"])
        self.assertTrue(any("PO-8841" in a["text"] and "suspended" in a["text"] for a in F["recovery"]["actions"]))

    def test_suspended_supplier_lot_is_held(self):
        S = data.build("baseline"); S["suppliers"]["S-03"]["audit"] = "Suspended"
        F = agents.analyze(S).findings; held = {h["lot"] for h in F["expiry"]["held"]}
        self.assertIn("L-PCM-007", held); self.assertNotIn("L-PCM-007", {a["lot"] for a in F["expiry"]["allocations"]})
        self.assertIn("QA review of held lots", F["guard"]["review"])

    def test_batch_level_traceability(self):
        S = data.build("quality"); t = agents.search(S, "L-AZI-102"); ids = {n["id"] for n in t["nodes"]}
        self.assertIn("B-AZI-2401", ids); self.assertIn("B-AZI-2402A", ids); self.assertNotIn("B-AZI-2402B", ids)   # exact, not order-level
        self.assertIn("L-AZI-101", {n["id"] for n in agents.search(S, "B-AZI-2402B")["nodes"]})
        self.assertFalse(agents.search(S, "NOPE")["found"])
        T = run("quality")["trace"]; self.assertEqual(T["affected_batches"], ["B-AZI-2401", "B-AZI-2402A"]); self.assertEqual(T["scope_cleared"], 1)
        self.assertEqual((T["handoff"]["hold_k"], T["handoff"]["recall_k"]), (40.0, 70.0))

    def test_lumpy_demand(self):
        F = run("baseline"); d = dox(F)
        self.assertEqual(d["demand_class"], "lumpy"); self.assertEqual(d["method"], "SBA rate + burst safety stock"); self.assertGreater(d["safety_k"], 0)
        self.assertEqual({i["demand_class"] for i in F["demand"]["items"] if i["med"] != "MED-DOX100"}, {"smooth"})
        self.assertGreater(d["selling_days"], 0); self.assertLess(d["selling_days"], len(d["daily"]) / 3)
        L = run("lumpy"); dl = dox(L)
        self.assertEqual(dl["pattern"], "spike"); self.assertEqual(dl["stockout_risk"], "High"); self.assertGreater(dl["forecast"], d["forecast"])
        self.assertTrue(L["material"]["shortages"]); self.assertEqual(L["material"]["shortages"][0]["api"], "API-DOX")
        a, b = agents.classify([0, 0, 5, 0, 0, 6, 0, 0, 5, 0]), agents.classify([4, 5, 4, 5, 4, 5])
        self.assertEqual((a[0], b[0]), ("intermittent", "smooth")); self.assertEqual(agents.sba([0, 0, 0]), 0.0)

    def test_supplier_grades_and_inspection(self):
        g = {s["id"]: s["grade"] for s in run("baseline")["material"]["suppliers"]}
        self.assertEqual((g["S-01"], g["S-04"]), ("A", "C")); self.assertEqual({s["id"]: s["grade"] for s in run("quality")["material"]["suppliers"]}["S-02"], "D")
        for d_ in run("surge")["recovery"]["drafts"]: self.assertIn("inspection level", d_["body"].lower())
        for rk in run("surge")["material"]["ranking"].values():
            for r in rk: self.assertTrue(any("never replaces inspection or QC release" in x for x in r["reasons"]))

    def test_use_in_time(self):
        u = run("expiry")["expiry"]["use_in_time"]; self.assertTrue(u); self.assertEqual(u[0]["lot"], "L-AZI-101")
        S = data.build("expiry"); S["lots"] = [dict(l, exp=10) if l["id"] == "L-AZI-101" else l for l in S["lots"]]
        self.assertEqual(next(x for x in agents.analyze(S).findings["expiry"]["use_in_time"] if x["lot"] == "L-AZI-101")["status"], "At risk")

    def test_quality_safeguard_in_rfq(self):
        for d_ in run("surge")["recovery"]["drafts"]: self.assertIn("incoming inspection", d_["body"].lower()); self.assertIn("not a purchase order", d_["body"].lower())

    def test_datasets_consistent(self):
        B = data.BASE; lots = {l["id"] for l in B["lots"]}; orders = {o["id"] for o in B["orders"]}; bt = {b["id"]: b for b in B["batches"]}
        for c in B["consumption"]: self.assertIn(c["lot"], lots); self.assertIn(c["order"], orders)
        for b in B["batches"]: self.assertIn(b["order"], orders)
        for l in B["lots"]: self.assertIn(l["sup"], B["suppliers"]); self.assertIn(l["api"], B["suppliers"][l["sup"]]["apis"]); self.assertLessEqual(sum(c["kg"] for c in B["consumption"] if c["lot"] == l["id"]), l["recv"])
        for c in B["consumption"]:   # batch-level usage adds up to order-level consumption
            ob = [b for b in B["batches"] if b["order"] == c["order"]]
            if all(b["usage"] for b in ob) and ob: self.assertEqual(sum(u["kg"] for b in ob for u in b["usage"] if u["lot"] == c["lot"]), c["kg"])
        for b in B["batches"]:   # dispatch adds up to batch size
            self.assertAlmostEqual(sum(x["units_k"] for x in b["dispatch"]), b["size_k"], places=1)
        for k, v in B["demand_full"].items(): self.assertEqual(len(v), 26)
        for k, v in B["daily"].items():
            self.assertEqual(len(v), 84)
            if k != "MED-DOX100": self.assertAlmostEqual(sum(v[-7:]), B["demand"][k][-1], places=1)

if __name__ == "__main__": unittest.main()
