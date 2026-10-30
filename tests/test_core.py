"""Run: python -m unittest discover -s tests   (standard library only)"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import agents, data

def run(s, b=1000000, w=4): return agents.analyze(data.build(s, b, w)).findings

class Core(unittest.TestCase):
    def test_deterministic(self):
        a, b = run("combined"), run("combined")
        self.assertEqual(a["recovery"]["total_cost"], b["recovery"]["total_cost"])
        self.assertEqual(a["recovery"]["actions"], b["recovery"]["actions"])

    def test_scenarios_change_outputs(self):
        base = run("baseline")
        self.assertEqual(base["recovery"]["total_cost"], 0)
        self.assertTrue(run("surge")["demand"]["handoff"]["spikes"])
        self.assertTrue(run("disruption")["material"]["delayed_pos"])
        self.assertTrue(run("expiry")["expiry"]["near_qty"] > 0)
        self.assertTrue(run("quality")["trace"]["affected_batches"])
        self.assertEqual(run("combined")["guard"]["status"], "REVIEW")

    def test_budget_and_horizon_change_recommendation(self):
        self.assertNotEqual(run("combined", 500000)["recovery"]["total_cost"], run("combined", 1500000)["recovery"]["total_cost"])
        self.assertLessEqual(run("combined", 500000)["recovery"]["total_cost"], 500000)
        self.assertNotEqual(run("surge", w=2)["demand"]["items"][1]["forecast"], run("surge", w=6)["demand"]["items"][1]["forecast"])

    def test_never_allocates_bad_lots(self):
        for s in data.SCENARIOS:
            F = run(s); lots = {l["id"]: l for l in F["expiry"]["lots"]}
            for a in F["expiry"]["allocations"]:
                self.assertEqual(lots[a["lot"]]["status"], "Released"); self.assertGreaterEqual(lots[a["lot"]]["days"], 0)
        ex = {e["lot"] for e in run("quality")["expiry"]["excluded"]}
        self.assertTrue({"L-AZI-102", "L-PCM-009", "L-MET-QC"} <= ex)

    def test_fefo_order(self):
        al = [a for a in run("baseline")["expiry"]["allocations"] if a["api"] == "API-MET"]
        self.assertEqual([a["days"] for a in al], sorted(a["days"] for a in al))

    def test_suspended_supplier_never_chosen(self):
        F = run("quality")
        for c in F["recovery"]["chosen"]:
            for l in c["lines"]: self.assertNotEqual(l["sup"], "S-02")
        rk = next(iter(F["material"]["ranking"].values()))
        self.assertFalse([r for r in rk if r["sup"] == "S-02"][0]["eligible"])

    def test_traceability(self):
        S = data.build("quality"); t = agents.search(S, "L-AZI-102")
        self.assertTrue(t["found"]); self.assertIn("B-AZI-2402A", {n["id"] for n in t["nodes"]})
        back = agents.search(S, "B-AZI-2402B"); self.assertIn("L-AZI-101", {n["id"] for n in back["nodes"]})
        self.assertFalse(agents.search(S, "NOPE")["found"])

    def test_quality_safeguard_in_rfq_and_ranking(self):
        F = run("surge")
        self.assertTrue(F["recovery"]["drafts"])
        for d in F["recovery"]["drafts"]: self.assertIn("incoming inspection", d["body"].lower()); self.assertIn("not a purchase order", d["body"].lower())
        for rk in F["material"]["ranking"].values():
            for r in rk: self.assertTrue(any("incoming inspection and QC release remain mandatory" in x for x in r["reasons"]))

    def test_datasets_consistent(self):
        B = data.BASE; lots = {l["id"] for l in B["lots"]}; orders = {o["id"] for o in B["orders"]}
        for c in B["consumption"]: self.assertIn(c["lot"], lots); self.assertIn(c["order"], orders)
        for b in B["batches"]: self.assertIn(b["order"], orders)
        for l in B["lots"]: self.assertIn(l["sup"], B["suppliers"]); self.assertIn(l["api"], B["suppliers"][l["sup"]]["apis"])
        for l in B["lots"]:
            used = sum(c["kg"] for c in B["consumption"] if c["lot"] == l["id"]); self.assertLessEqual(used, l["recv"])
        for k, v in B["demand_full"].items(): self.assertEqual(len(v), 26)




if __name__ == "__main__": unittest.main()
