"""Shared service layer used by both UIs (server.py + static page, and streamlit_app.py).
Runs the agent pipeline in a background thread, persists recommendations, handles approval and execution."""
import csv, io, json, os, threading
from . import agents, data, store

store.load_env(); store.conn()
def _last_rec():   # continue numbering after restarts so earlier recommendations and audit rows are never overwritten
    r = store.q("SELECT MAX(CAST(SUBSTR(id,5) AS INTEGER)) m FROM recs"); return int(r[0]["m"] or 0)
RUNS, _n = {}, [_last_rec()]

def mk_state(p): return data.build(p.get("scenario", "baseline"), float(p.get("budget") or 1000000), int(p.get("weeks") or 4))

def execute(run, rec_id):
    store.audit("run_started", "orchestrator", rec_id, None, "ok", f"scenario={run.S['scenario']} budget={run.S['budget']:.0f} weeks={run.S['weeks']}")
    last = [0]
    def flush():
        for e in run.events[last[0]:]:
            if e["type"] == "status" and any(s in e["text"] for s in ("completed", "attention", "blocked")):
                store.audit("agent_" + e["text"].split(": ")[1], e["agent"], rec_id, None, "ok", e["text"])
        last[0] = len(run.events)
    agents.run_pipeline(run); flush()
    if run.status == "failed":
        store.audit("run_failed", run.error, rec_id, None, "failed", "agent error; retry available"); return
    finalize(run, rec_id)

def finalize(run, rec_id):
    F = run.findings; g, R = F["guard"], F["recovery"]
    for d in R["drafts"]: d["subject"] = d["subject"].replace("{REC_ID}", rec_id); d["body"] = d["body"].replace("{REC_ID}", rec_id)
    payload = dict(scenario=run.S["scenario"], budget=run.S["budget"], recovery=R, guard=g, trace=F["trace"]["summary"], demand=F["demand"]["summary"], material=F["material"]["summary"], expiry=F["expiry"]["summary"])
    store.x("INSERT OR REPLACE INTO recs(id,ts,run_id,scenario,budget,status,guard_status,payload) VALUES(?,?,?,?,?,?,?,?)",
            (rec_id, store.now(), run.id, run.S["scenario"], run.S["budget"], "pending", g["status"], json.dumps(payload)))
    store.audit("recommendation_created", "recovery_agent", rec_id, None, g["status"], f"cost={R['total_cost']} coverage={R['coverage']}")
    store.audit("validation", "quality_guard", rec_id, None, g["status"], "; ".join(g["review"]) or "no review items")
    store.notify("warning", "approval_required", f"{rec_id} requires approval (validation {g['status']})", rec_id, run.id, rec_id)
    crit = [n for n in run.notes if n["sev"] == "critical"]; to = store.setting("reviewer_email")
    if not to: store.audit("email_skipped", "email_service", rec_id, None, "skipped", "reviewer email not set")
    elif crit or g["status"] != "PASS":
        body = f"{rec_id} ({run.S['scenario']}) awaits your decision.\nValidation: {g['status']}\nTotal procurement: Rs {R['total_cost']:,.0f}\n\nCritical items:\n" + "\n".join("- " + n["msg"] for n in crit) + "\n\nOpen MedChain AI > Decisions & Audit to approve or reject."
        store.queue_email(rec_id, "reviewer_alert", to, f"[MedChain] {rec_id}: approval required ({len(crit)} critical)", body)

def start_run(p, S=None):
    _n[0] += 1; rec_id = f"REC-{_n[0]:04d}"; S = S or mk_state(p)
    run = agents.Run(S); run.id = f"RUN-{_n[0]:04d}"; run.rec_id = rec_id
    run.on_notify = lambda n: store.notify(n["sev"], n["kind"], n["msg"], n["entity"], run.id, rec_id)
    RUNS[run.id] = run; threading.Thread(target=execute, args=(run, rec_id), daemon=True).start(); return run

def run_view(run, since=0):
    return dict(id=run.id, rec_id=run.rec_id, status=run.status, error=run.error, scenario=run.S["scenario"], agents=run.agents,
                events=[e for e in run.events if e["seq"] > since], seq=run.seq)

def decide(rec_id, b):
    r = store.q("SELECT * FROM recs WHERE id=?", (rec_id,))
    if not r: return 404, {"error": "unknown recommendation"}
    r = r[0]; P = json.loads(r["payload"]); dec = b.get("decision"); comment = (b.get("comment") or "").strip()
    if r["status"] not in ("pending", "revision_requested"): return 409, {"error": f"already {r['status']}"}
    if dec == "approve":
        if r["guard_status"] == "BLOCKED": return 409, {"error": "Quality Guard blocked this plan; it cannot be approved"}
        if r["guard_status"] == "REVIEW" and not comment: return 400, {"error": "Validation requires review: add a reviewer comment to approve"}
        emails = b.get("emails") or P["recovery"]["drafts"]; results = []
        store.x("UPDATE recs SET status='approved', comment=?, decided_ts=? WHERE id=?", (comment, store.now(), rec_id))
        store.audit("human_approved", "reviewer", rec_id, None, "approved", comment or "no comment")
        for e in emails:
            row = store.queue_email(rec_id, "supplier_rfq", e["to"], e["subject"], e["body"], e.get("supplier_id")); results.append(row["status"])
            store.audit("execution_supplier_rfq", "system", rec_id, e.get("supplier_id"), row["status"], f"RFQ (not a purchase order) to {e['to']}")
        ex = "no external action" if not emails else ("supplier emails sent" if all(s == "sent" for s in results) else "supplier email failed: retry available")
        store.x("UPDATE recs SET exec_status=? WHERE id=?", (ex, rec_id)); store.notify("info" if "failed" not in ex else "critical", "action_executed", f"{rec_id}: {ex}", rec_id, None, rec_id)
    elif dec in ("reject", "revise"):
        st = "rejected" if dec == "reject" else "revision_requested"
        store.x("UPDATE recs SET status=?, comment=?, decided_ts=?, exec_status='none executed' WHERE id=?", (st, comment, store.now(), rec_id))
        store.audit("human_" + st, "reviewer", rec_id, None, st, comment or "no comment")
    else: return 400, {"error": "decision must be approve, reject or revise"}
    to = store.setting("reviewer_email")
    if to: store.queue_email(rec_id, "decision_notice", to, f"[MedChain] {rec_id} {dec}", f"Decision recorded for {rec_id}: {dec}.\nComment: {comment or '-'}")
    return 200, store.q("SELECT * FROM recs WHERE id=?", (rec_id,))[0]

def upload_demand(b):
    """Apply or reset a demand CSV upload. Returns (http_code, body)."""
    if b.get("reset"):
        data.OVERRIDE.clear(); store.audit("demand_upload_reset", "reviewer", None, None, "ok", "bundled demand restored"); return 200, {"ok": True}
    rows = {}
    try:
        for r in csv.DictReader(io.StringIO(b.get("csv", ""))):
            if r.get("medicine_id") in data.BASE["medicines"]: rows.setdefault(r["medicine_id"], []).append(float(r.get("demand_k") or r["demand_k_tablets"]))
    except (ValueError, KeyError, TypeError): rows = {}
    bad = [k for k, v in rows.items() if len(v) < 6]
    if not rows or bad: return 400, {"error": "CSV needs columns medicine_id,demand_k (or demand_k_tablets; oldest first), known IDs " + ", ".join(data.BASE["medicines"]) + ", and at least 6 rows per medicine"}
    data.OVERRIDE.update(rows); store.audit("demand_uploaded", "reviewer", None, None, "ok", "; ".join(f"{k}: {len(v)} weeks" for k, v in rows.items()))
    return 200, {"ok": True, "medicines": sorted(rows)}

def retry_agent(run, k):
    """Re-run the pipeline from one agent onward (used after an agent error)."""
    store.audit("agent_retry", "reviewer", run.rec_id, None, "requested", k)
    i = agents.ORDER.index(k)
    threading.Thread(target=lambda: (agents.run_pipeline(run, i), finalize(run, run.rec_id) if run.status == "completed" else None), daemon=True).start()
