"""MedChain AI server (Python standard library only). Run: python server.py"""
import json, os, sys, threading, math
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import agents, data, store

from app import service
from app.service import RUNS, mk_state, start_run, run_view, decide, finalize, upload_demand
STATIC = os.path.join(store.ROOT, "static")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def body(self):
        n = int(self.headers.get("Content-Length") or 0); return json.loads(self.rfile.read(n) or b"{}") if n else {}
    def do_GET(self): self.route("GET")
    def do_POST(self): self.route("POST")
    def route(self, m):
        u = urlparse(self.path); p = {k: v[0] for k, v in parse_qs(u.query).items()}; path = u.path
        try:
            if not path.startswith("/api/"):
                f = os.path.join(STATIC, "index.html" if path == "/" else path.lstrip("/"))
                if not os.path.abspath(f).startswith(STATIC) or not os.path.isfile(f): return self.send(404, {"error": "not found"})
                return self.send(200, open(f, "rb").read(), "text/html; charset=utf-8" if f.endswith(".html") else "text/plain")
            b = self.body() if m == "POST" else {}; code, out = 200, None
            if path == "/api/meta":
                c = store.smtp_cfg(); out = dict(scenarios={k: dict(name=v[0], desc=v[1]) for k, v in data.SCENARIOS.items()}, as_of=data.AS_OF.isoformat(),
                    smtp_configured=c["configured"], smtp=dict(host=c["host"], port=c["port"], user=c["user"], sender=c["sender"], security=c["security"]), reviewer_email=store.setting("reviewer_email"),  custom_demand=sorted(data.OVERRIDE))
            elif path == "/api/analysis":
                S = mk_state(p); r = agents.analyze(S); F = r.findings
                out = dict(F=F, health=agents.health(F), alerts=r.notes, scenario=S["scenario"], budget=S["budget"], suppliers_master=S["suppliers"], orders=S["orders"], batches=S["batches"], pos=S["pos"])
            elif path == "/api/upload/demand": code, out = upload_demand(b)
            elif path == "/api/datasets": out = data.catalog()
            elif path == "/api/dataset":
                name = p.get("name", ""); ok = {x["file"] for x in data.catalog()} | {"demand_upload_example_surge.csv"}
                if name not in ok: code, out = 404, {"error": "unknown dataset"}
                else: return self.send(200, open(os.path.join(store.ROOT, "uploads_examples" if name.startswith("demand_upload") else "datasets", name), "rb").read(), "text/csv; charset=utf-8")
            elif path == "/api/trace": out = agents.search(mk_state(p), p.get("q", ""))
            elif path == "/api/run" and m == "POST": out = run_view(start_run({**p, **b}))
            elif path.startswith("/api/run/"):
                parts = path.split("/"); run = RUNS.get(parts[3])
                if not run: code, out = 404, {"error": "unknown run (server restarted?)"}
                elif len(parts) == 5 and parts[4] == "retry":
                    service.retry_agent(run, b.get("agent")); out = {"ok": True}
                else: out = run_view(run, int(p.get("since", 0)))
            elif path == "/api/notifications" and m == "GET": out = dict(items=store.q("SELECT * FROM notifications ORDER BY id DESC LIMIT 100"), unread=store.q("SELECT COUNT(*) c FROM notifications WHERE read=0")[0]["c"])
            elif path == "/api/notifications/read": store.x("UPDATE notifications SET read=1" + ("" if b.get("all") else " WHERE id=%d" % int(b["id"]))); out = {"ok": True}
            elif path == "/api/recs":
                out = store.q("SELECT id,ts,run_id,scenario,budget,status,exec_status,guard_status,comment,decided_ts,payload FROM recs ORDER BY ts DESC, id DESC")
                for r in out: r["payload"] = json.loads(r["payload"])
            elif path.startswith("/api/rec/") and path.endswith("/decide"): code, out = decide(path.split("/")[3], b)
            elif path == "/api/emails": out = store.q("SELECT * FROM emails ORDER BY id DESC LIMIT 100")
            elif path.startswith("/api/email/") and path.endswith("/retry"):
                eid = int(path.split("/")[3]); store.audit("email_retry", "reviewer", None, None, "requested", f"email #{eid}"); out = store.deliver(eid)
            elif path == "/api/email/test": out = store.queue_email(None, "test", b.get("to", ""), "[MedChain] SMTP test", "SMTP configuration test from MedChain AI.")
            elif path == "/api/audit":
                w, a = [], []
                for k, col in (("rec", "rec_id"), ("type", "event_type"), ("supplier", "supplier_id")):
                    if p.get(k): w.append(f"{col}=?"); a.append(p[k])
                out = store.q("SELECT * FROM audit" + (" WHERE " + " AND ".join(w) if w else "") + " ORDER BY id DESC LIMIT 300", a)
            elif path == "/api/settings" and m == "POST":
                for k in ("reviewer_email", "smtp_host", "smtp_port", "smtp_user", "smtp_from", "smtp_security"):
                    if k in b: store.set_setting(k, str(b[k]).strip())
                if b.get("smtp_password"): store.set_setting("smtp_password", b["smtp_password"])
                store.audit("settings_changed", "reviewer", None, None, "ok", "reviewer/SMTP settings updated"); out = {"ok": True}
            else: code, out = 404, {"error": "unknown endpoint"}
            self.send(code, out)
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": f"{type(e).__name__}: {e}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)); print(f"MedChain AI running at http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
