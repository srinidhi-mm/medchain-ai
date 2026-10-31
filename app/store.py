"""SQLite persistence, audit trail, notifications and SMTP email delivery."""
import os, re, smtplib, sqlite3, ssl, threading, time
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "medchain.db")
_lock, _c = threading.RLock(), None
now = lambda: time.strftime("%Y-%m-%d %H:%M:%S")

def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))

def conn():
    global _c
    if _c is None:
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        _c = sqlite3.connect(DB, check_same_thread=False); _c.row_factory = sqlite3.Row
        _c.executescript("""
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, ts TEXT, sev TEXT, kind TEXT, msg TEXT, entity TEXT, run_id TEXT, rec_id TEXT, read INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, event_type TEXT, actor TEXT, rec_id TEXT, supplier_id TEXT, outcome TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS recs(id TEXT PRIMARY KEY, ts TEXT, run_id TEXT, scenario TEXT, budget REAL, status TEXT, exec_status TEXT, guard_status TEXT, payload TEXT, comment TEXT, decided_ts TEXT);
        CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY, ts TEXT, rec_id TEXT, kind TEXT, to_addr TEXT, subject TEXT, body TEXT, supplier_id TEXT, status TEXT, error TEXT, attempts INTEGER DEFAULT 0, last_ts TEXT);
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);""")
    return _c

def q(sql, a=()):
    with _lock:
        cur = conn().execute(sql, a); conn().commit()
        return [dict(r) for r in cur.fetchall()] if cur.description else []
def x(sql, a=()):
    with _lock:
        cur = conn().execute(sql, a); conn().commit(); return cur.lastrowid

def audit(event_type, actor, rec_id=None, supplier_id=None, outcome="ok", detail=""):
    x("INSERT INTO audit(ts,event_type,actor,rec_id,supplier_id,outcome,detail) VALUES(?,?,?,?,?,?,?)", (now(), event_type, actor, rec_id, supplier_id, outcome, detail))
def notify(sev, kind, msg, entity=None, run_id=None, rec_id=None):
    x("INSERT INTO notifications(ts,sev,kind,msg,entity,run_id,rec_id) VALUES(?,?,?,?,?,?,?)", (now(), sev, kind, msg, entity, run_id, rec_id))

def setting(k, default=""):
    r = q("SELECT v FROM settings WHERE k=?", (k,)); return r[0]["v"] if r else default
def set_setting(k, v): x("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

def smtp_cfg():
    g = lambda k, e, dflt="": setting(k) or os.environ.get(e, dflt)
    c = dict(host=g("smtp_host", "SMTP_HOST"), port=int(g("smtp_port", "SMTP_PORT", "587") or 587), user=g("smtp_user", "SMTP_USER"),
             password=g("smtp_password", "SMTP_PASSWORD"), sender=g("smtp_from", "SMTP_FROM"), security=g("smtp_security", "SMTP_SECURITY", "starttls"))
    c["sender"] = c["sender"] or c["user"]; c["configured"] = bool(c["host"] and c["sender"]); return c

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def queue_email(rec_id, kind, to, subject, body, supplier_id=None):
    eid = x("INSERT INTO emails(ts,rec_id,kind,to_addr,subject,body,supplier_id,status,attempts) VALUES(?,?,?,?,?,?,?,?,0)", (now(), rec_id, kind, to, subject, body, supplier_id, "pending"))
    return deliver(eid)

def deliver(eid):
    """Attempt SMTP delivery. Status is 'sent' only if the server accepted the message."""
    r = q("SELECT * FROM emails WHERE id=?", (eid,))[0]; c = smtp_cfg(); err = None
    if not EMAIL_RE.match(r["to_addr"] or ""): err = "Invalid recipient address"
    elif not c["configured"]: err = "SMTP not configured (set SMTP_HOST and SMTP_FROM in .env or Settings)"
    else:
        try:
            m = EmailMessage(); m["From"], m["To"], m["Subject"] = c["sender"], r["to_addr"], r["subject"]; m.set_content(r["body"])
            if c["security"] == "ssl": s = smtplib.SMTP_SSL(c["host"], c["port"], timeout=15, context=ssl.create_default_context())
            else:
                s = smtplib.SMTP(c["host"], c["port"], timeout=15)
                if c["security"] == "starttls": s.starttls(context=ssl.create_default_context())
            if c["user"]: s.login(c["user"], c["password"])
            s.send_message(m); s.quit()
        except Exception as e: err = f"{type(e).__name__}: {e}"
    st = "failed" if err else "sent"
    x("UPDATE emails SET status=?, error=?, attempts=attempts+1, last_ts=? WHERE id=?", (st, err, now(), eid))
    audit("email_" + st, "email_service", r["rec_id"], r["supplier_id"], st, f"{r['kind']} to {r['to_addr']}" + (f": {err}" if err else ""))
    notify("info" if st == "sent" else "critical", "email_status", f"Email ({r['kind']}) to {r['to_addr']} {st}" + (f": {err}" if err else ""), r["supplier_id"], None, r["rec_id"])
    return q("SELECT * FROM emails WHERE id=?", (eid,))[0]
