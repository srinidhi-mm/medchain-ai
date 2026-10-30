"""MedChain AI - Streamlit UI.  Run: streamlit run streamlit_app.py
Uses the same agents, dataset, SQLite store and approval/email logic as the standard-library server."""
import json, os, sys, time
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import agents, data, service, store
from app.service import RUNS, mk_state, start_run, decide, upload_demand

st.set_page_config(page_title="MedChain AI", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.block-container{padding-top:2rem;max-width:1320px}
[data-testid="stMetricValue"]{color:#6b4a2f}
[data-testid="stSidebar"]{border-right:1px solid #e7ddd0}
h1,h2,h3,h4{color:#6b4a2f;font-weight:600}
</style>""", unsafe_allow_html=True)

PAGES = ["Command Center", "Agent Workspace", "Supply & Traceability", "Decisions & Audit"]
SUBS = ["Inventory & expiry", "Suppliers", "FEFO allocation", "Production impact", "Batch traceability"]
AG = agents.ORDER
LB = agents.LABEL
DEPS = agents.DEPS
POS = {"demand": (150, 80), "material": (380, 45), "expiry": (610, 80), "trace": (610, 380), "recovery": (380, 415), "guard": (150, 380)}
STC = {"idle": "#b8a99a", "waiting": "#c98a2b", "analyzing": "#6b4a2f", "completed": "#4f7a4a", "attention": "#c98a2b", "blocked": "#b3412e"}
BADGE = {**{k: "green" for k in ("Released", "Approved", "pass", "PASS", "sent", "approved", "Low", "OK", "completed", "fits", "info")},
         **{k: "orange" for k in ("Quarantine", "Conditional", "REVIEW", "warn", "Medium", "Near expiry", "pending", "waiting", "attention", "revision_requested", "Planned", "In progress")},
         **{k: "red" for k in ("failed", "Rejected", "Suspended", "Expired", "BLOCKED", "fail", "High", "rejected", "blocked", "over", "critical")},
         "analyzing": "blue"}
PX = dict(font=dict(family="Georgia, serif", color="#2b2118"), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", margin=dict(l=10, r=10, t=30, b=10))


def badge(s): return f":{BADGE.get(s, 'gray')}-badge[{s}]"


def inr(v):
    s, neg = str(int(round(abs(v)))), v < 0
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "Rs " + s


def flash(kind, msg): st.session_state["_flash"] = (kind, msg)


def show_flash():
    f = st.session_state.pop("_flash", None)
    if f: getattr(st, f[0])(f[1])


def goto(page, sub=None, **kw):
    st.session_state["nav"] = page
    if sub: st.session_state["sp_sub"] = sub
    for k, v in kw.items(): st.session_state[k] = v


def recs():
    out = store.q("SELECT id,ts,run_id,scenario,budget,status,exec_status,guard_status,comment,decided_ts,payload FROM recs ORDER BY ts DESC, id DESC")
    for r in out: r["payload"] = json.loads(r["payload"])
    return out


# ------------------------------------------------------------------ sidebar and shared state
st.sidebar.markdown("### MedChain AI")
st.sidebar.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
SC_IDS = list(data.SCENARIOS)
st.sidebar.selectbox("Scenario", SC_IDS, index=SC_IDS.index("combined"), format_func=lambda k: data.SCENARIOS[k][0], key="sc")
st.sidebar.number_input("Budget (INR)", min_value=100000, max_value=5000000, value=1000000, step=50000, key="budget")
st.sidebar.selectbox("Horizon (weeks)", [2, 4, 6], index=1, key="weeks")
SC, BUDGET, WEEKS = st.session_state["sc"], float(st.session_state["budget"]), int(st.session_state["weeks"])
SIG = (SC, BUDGET, WEEKS, tuple(sorted((k, tuple(v)) for k, v in data.OVERRIDE.items())))

RUN_ = agents.analyze(mk_state(dict(scenario=SC, budget=BUDGET, weeks=WEEKS)))   # recalculated on every change
F, ALERTS, HEALTH = RUN_.findings, RUN_.notes, agents.health(RUN_.findings)

nf = store.q("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")
unread = sum(1 for n in nf if not n["read"])
with st.sidebar.expander(f"Notifications ({unread} unread)", expanded=False):
    for n in nf[:8]:
        st.markdown(f"{badge(n['sev'])} **{n['kind'].replace('_', ' ')}** `{n['ts'][11:]}`  \n{n['msg']}")
    c1, c2 = st.columns(2)
    c1.button("Mark all read", on_click=lambda: store.x("UPDATE notifications SET read=1"), key="nf_all")
    c2.button("Open decisions", on_click=goto, args=("Decisions & Audit",), key="nf_open")
st.sidebar.caption("Synthetic, fixed data. Recalculates on every change; no live market feeds.")


# ------------------------------------------------------------------ Command Center
def page_cc():
    D, M, E, T = F["demand"]["items"], F["material"], F["expiry"], F["trace"]
    pend = [r for r in recs() if r["status"] == "pending"]
    flagged = [i for i in D if i["pattern"] != "normal" or i["stockout_risk"] == "High"]
    top = max(M["suppliers"], key=lambda s: s["risk"])
    c1, c2 = st.columns([1, 2])
    with c1:
        col = "#4f7a4a" if HEALTH >= 75 else "#c98a2b" if HEALTH >= 50 else "#b3412e"
        g = go.Figure(go.Indicator(mode="gauge+number", value=HEALTH, title={"text": "Supply-chain health"},
                                   gauge=dict(axis=dict(range=[0, 100]), bar=dict(color=col), bgcolor="#f3ebe1", borderwidth=0)))
        g.update_layout(height=230, **PX); st.plotly_chart(g, width="stretch", key="cc_gauge")
    with c2:
        st.subheader(data.SCENARIOS[SC][0]); st.write(data.SCENARIOS[SC][1])
        st.button("Run agents on this scenario", type="primary", on_click=goto, args=("Agent Workspace",), kwargs=dict(auto_start=True), key="cc_run")
    t = st.columns(4)
    tiles = [("Demand risk", len(flagged), ", ".join(i["name"].split()[0] for i in flagged) or "stable", "High" if flagged else "Low", ("Agent Workspace", None)),
             ("Supplier risk", top["risk"], top["name"].split()[0] + (" delayed" if top["delay_days"] else ""), top["level"], ("Supply & Traceability", "Suppliers")),
             ("Projected wastage", inr(E["wastage_value"]), f"{E['near_qty']} kg near expiry", E["risk"], ("Supply & Traceability", "Inventory & expiry")),
             ("Production impact", len(T["affected_batches"]) + len(T["delayed_orders"]), f"{len(T['affected_batches'])} batches, {len(T['delayed_orders'])} orders",
              "High" if T["affected_batches"] else "Medium" if T["delayed_orders"] else "Low", ("Supply & Traceability", "Production impact"))]
    for c, (title, val, sub, lvl, dest) in zip(t, tiles):
        with c.container(border=True):
            st.metric(title, val); st.markdown(f"{badge(lvl)} {sub}")
            st.button("Details", key=f"tile_{title}", on_click=goto, args=(dest[0], dest[1]))
    a, b = st.columns([3, 2])
    with a:
        med = st.segmented_control("Medicine", [i["med"] for i in D], default=(flagged[0] if flagged else D[0])["med"], format_func=lambda m: next(i["name"].split()[0] for i in D if i["med"] == m), key="dmed") or D[0]["med"]
        it = next(i for i in D if i["med"] == med)
        last = data.AS_OF - timedelta(days=6); h = it["history"]; n = len(h)
        xs = [last - timedelta(weeks=n - 1 - i) for i in range(n)]; fx = [last + timedelta(weeks=i) for i in range(0, WEEKS + 1)]
        half = (it["high"] - it["forecast"]) / (WEEKS ** 0.5)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=fx, y=[it["level"] + half] * len(fx), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fx, y=[max(0, it["level"] - half)] * len(fx), mode="lines", fill="tonexty", fillcolor="rgba(164,113,72,.15)", line=dict(width=0), name="80% band", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=xs, y=h, mode="lines+markers", name="History", line=dict(color="#6b4a2f", width=2)))
        fig.add_trace(go.Scatter(x=[xs[-1]] + fx[1:], y=[h[-1]] + [it["level"]] * WEEKS, name="Forecast", line=dict(color="#a47148", dash="dash", width=2)))
        fig.add_hline(y=it["baseline"], line=dict(color="#c9b9a6", dash="dot"), annotation_text="baseline", annotation_position="bottom left")
        fig.update_layout(height=300, yaxis_title="thousand tablets / week", legend=dict(orientation="h", y=1.12), **PX)
        st.plotly_chart(fig, width="stretch", key="cc_demand")
        st.caption(f"Level {it['level']}k vs baseline {it['baseline']}k (z {it['z']}); cover {it['cover_weeks']} wk; replenish {it['replenish_k']}k units ({it['required_kg']} kg API). "
                   f"Forecast {it['forecast']}k over {WEEKS} wk (band {it['low']}-{it['high']}k).")
    with b:
        sp = sorted(M["suppliers"], key=lambda s: s["risk"])
        f2 = go.Figure(go.Bar(x=[s["risk"] for s in sp], y=[s["name"] for s in sp], orientation="h",
                              marker_color=["#b3412e" if s["level"] == "High" else "#c98a2b" if s["level"] == "Medium" else "#4f7a4a" for s in sp], text=[s["risk"] for s in sp]))
        f2.update_layout(height=300, title="Supplier risk score", xaxis=dict(range=[0, 100]), **PX); st.plotly_chart(f2, width="stretch", key="cc_sup")
    x, y, z = st.columns(3)
    with x:
        st.markdown("#### High-priority alerts")
        for al in [a_ for a_ in ALERTS if a_["sev"] != "info"][:7]: st.markdown(f"{badge(al['sev'])} {al['msg']}")
        if not [a_ for a_ in ALERTS if a_["sev"] != "info"]: st.caption("No alerts in this scenario.")
    with y:
        st.markdown("#### Workflows and approvals")
        st.write(f"{len(pend)} pending approval(s)")
        for r in recs()[:5]: st.markdown(f"**{r['id']}** {data.SCENARIOS[r['scenario']][0]} {badge(r['status'])} {badge(r['guard_status'])}")
        st.button("Open decisions", on_click=goto, args=("Decisions & Audit",), key="cc_dec")
    with z:
        st.markdown("#### Recent notifications")
        for n in nf[:5]: st.markdown(f"{badge(n['sev'])} {n['msg']}")
        if not nf: st.caption("None yet. Run the agents.")


# ------------------------------------------------------------------ Agent Workspace
def agent_graph(ag, sel, active):
    fig = go.Figure(); cx, cy = 380, 230
    for k in AG: fig.add_trace(go.Scatter(x=[cx, POS[k][0]], y=[cy, POS[k][1]], mode="lines", line=dict(color="#e7ddd0", width=1, dash="dot"), hoverinfo="skip", showlegend=False))
    for k in AG:
        for d in DEPS.get(k, []):
            on = (d, k) in active
            fig.add_trace(go.Scatter(x=[POS[d][0], POS[k][0]], y=[POS[d][1], POS[k][1]], mode="lines", line=dict(color="#6b4a2f" if on else "#d9ccbc", width=3.5 if on else 1.3), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[cx], y=[cy], mode="markers+text", text=["Orchestrator"], textfont=dict(size=11, color="#6b4a2f"), marker=dict(size=96, color="#faf6f1", line=dict(color="#6b4a2f", width=2)), hoverinfo="skip", showlegend=False))
    for k in AG:
        s = ag[k]["status"] if ag else "idle"; p = ag[k]["progress"] if ag else 0
        fig.add_trace(go.Scatter(x=[POS[k][0]], y=[POS[k][1]], mode="markers+text", text=[f"<b>{LB[k].replace(' & ', ' &<br>').replace('Production', 'Production<br>') if k in ('expiry', 'trace') else LB[k].replace(' ', '<br>', 1)}</b><br>{s}"],
                                 textfont=dict(size=10), marker=dict(size=92, color="#ffffff", line=dict(color=STC[s], width=7 if sel == k else 3)),
                                 hovertemplate=f"{LB[k]}<br>{s} ({p}%)<br>{agents.TASK[k]}<extra></extra>", showlegend=False))
    fig.update_layout(height=470, xaxis=dict(visible=False, range=[0, 760]), yaxis=dict(visible=False, range=[470, -10]), **PX)
    return fig


def begin_run():
    run = start_run(dict(scenario=SC, budget=BUDGET, weeks=WEEKS))
    st.session_state.update(run_id=run.id, run_sig=SIG, run_t0=time.time(), ws_was_busy=True)


def is_busy(run):
    if run.status in ("created", "running"): return True
    return run.status == "completed" and not store.q("SELECT 1 FROM recs WHERE id=?", (run.rec_id,)) and time.time() - st.session_state.get("run_t0", 0) < 20


def decision_box(run, rec, pfx):
    if not rec:
        if run.status == "failed": st.error(f"Workflow failed at {LB.get(run.error, run.error)}. Retry that agent.")
        else: st.caption("Agents are working. The recommendation appears here once the Quality Guard has validated it.")
        return
    P, R = rec["payload"], rec["payload"]["recovery"]
    st.markdown(f"**{rec['id']}** {badge(rec['guard_status'])} {badge(rec['status'])}")
    for s in R["summary"]: st.markdown(f"- {s}")
    for a in R["actions"]: st.markdown(f"**P{a['p']}.** {a['text']}")
    st.progress(min(1.0, R["total_cost"] / R["budget"]) if R["budget"] else 0, text=f"Cost {inr(R['total_cost'])} of {inr(R['budget'])}")
    for c in [c for c in P["guard"]["checks"] if c["result"] != "pass"]: st.markdown(f"{badge(c['result'])} {c['check']}: {c['detail']}")
    if rec["status"] in ("pending", "revision_requested"):
        approve_decision_widgets(rec, pfx)
        if R["drafts"]: st.caption("Supplier emails are sent as drafted. To edit them first, use Decisions & Audit."); st.button("Edit emails", on_click=goto, args=("Decisions & Audit",), key=f"{pfx}_edit_{rec['id']}")
    else: st.markdown(f"Decision: {badge(rec['status'])} {rec['exec_status'] or ''}")


def approve_decision_widgets(rec, pfx, with_emails=False):
    rid = rec["id"]; comment = st.text_area("Reviewer comment" + (" (required: validation needs review)" if rec["guard_status"] == "REVIEW" else ""), key=f"{pfx}_c_{rid}", height=70)
    b1, b2, b3 = st.columns(3)
    def act(dec):
        body = dict(decision=dec, comment=st.session_state.get(f"{pfx}_c_{rid}", ""))
        if with_emails and dec == "approve":
            body["emails"] = [dict(supplier_id=d["supplier_id"], to=st.session_state.get(f"em_{rid}_{i}_to", d["to"]), subject=st.session_state.get(f"em_{rid}_{i}_sub", d["subject"]),
                                   body=st.session_state.get(f"em_{rid}_{i}_body", d["body"])) for i, d in enumerate(rec["payload"]["recovery"]["drafts"])]
        code, out = decide(rid, body)
        flash("success" if code == 200 else "error", f"{rid}: {dec} recorded. {out.get('exec_status') or ''}" if code == 200 else out.get("error", "failed"))
    b1.button("Approve and execute", type="primary", disabled=rec["guard_status"] == "BLOCKED", key=f"{pfx}_ap_{rid}", on_click=act, args=("approve",))
    b2.button("Reject", key=f"{pfx}_rj_{rid}", on_click=act, args=("reject",))
    b3.button("Request revision", key=f"{pfx}_rv_{rid}", on_click=act, args=("revise",))


def live(run_id):
    run = RUNS[run_id]; ag = run.agents; busy = is_busy(run)
    if st.session_state.get("ws_was_busy") and not busy:
        st.session_state["ws_was_busy"] = False; st.rerun()
    evs = list(run.events); msgs = [e for e in evs if e["type"] == "message" and e["agent"] != "orchestrator"][-3:]
    active = {(m["agent"], m["data"]["to"]) for m in msgs}
    active |= {(d, k) for k in AG for d in DEPS.get(k, []) if ag[d]["progress"] == 100 and ag[k]["status"] == "analyzing"}
    left, right = st.columns([3, 2])
    sel = st.session_state.get("sel", "demand")
    with left:
        st.plotly_chart(agent_graph(ag, sel, active), width="stretch", key="ws_graph")
        st.caption(f"Orchestrator: {run.status} | run {run.id} | nodes show status; dark connections carry a handoff in progress")
    with right:
        st.segmented_control("Inspect agent", AG, format_func=LB.get, key="sel", default="demand"); sel = st.session_state.get("sel") or "demand"; a = ag[sel]
        st.markdown(f"#### {LB[sel]} {badge(a['status'])}"); st.caption(a["task"])
        if a["error"]: st.error(a["error"]); st.button("Retry this agent", key="ws_retry", on_click=service.retry_agent, args=(run, sel))
        for s in a["summary"]: st.markdown(f"- {s}")
        if a["input"]:
            with st.expander("Input received"): st.json(a["input"])
        if a["output"]:
            with st.expander("Structured output (handoff)"): st.json(a["output"])
    e1, e2 = st.columns([3, 2])
    with e1:
        st.markdown("#### Live event stream")
        flt = st.radio("Filter", ["All", "Messages", "Selected agent"], horizontal=True, key="ws_flt", label_visibility="collapsed")
        shown = [e for e in evs if flt == "All" or (flt == "Messages" and e["type"] == "message") or (flt == "Selected agent" and e["agent"] == sel)][-60:][::-1]
        with st.container(height=330):
            for e in shown:
                who = "" if e["agent"] == "orchestrator" or e["type"] in ("message", "status") else f"**{LB.get(e['agent'], e['agent'])}** "
                extra = f" `{json.dumps(e['data']['payload'])[:110]}`" if e["type"] == "message" and e["data"].get("payload") else ""
                st.markdown(f"`{e['t']}` {who}{e['text']}{extra}")
    with e2:
        st.markdown("#### Human decision")
        rec = next((r for r in recs() if r["id"] == run.rec_id), None)
        decision_box(run, rec, "ws")


def page_ws():
    show_flash()
    h1, h2 = st.columns([4, 1])
    h1.subheader("Agent Workspace"); h1.caption(f"{data.SCENARIOS[SC][0]} | budget {inr(BUDGET)} | {WEEKS} wk horizon")
    run = RUNS.get(st.session_state.get("run_id"))
    start = st.session_state.pop("auto_start", False)
    if h2.button("Run again" if run else "Start agent workflow", type="primary", key="ws_start") or start or (run is not None and st.session_state.get("run_sig") != SIG):
        begin_run(); run = RUNS[st.session_state["run_id"]]
    if run is None:
        st.info("Press Start to run the six agents on the selected scenario. Changing scenario, budget or horizon afterwards reruns them automatically."); return
    busy = is_busy(run); st.session_state["ws_was_busy"] = busy
    st.fragment(live, run_every=0.6 if busy else None)(run.id)


# ------------------------------------------------------------------ Supply & Traceability
def genealogy(T):
    if not T["found"]: st.error(f"No lot or batch matches \"{T['q']}\"."); return
    cols = {0: [], 1: [], 2: [], 3: []}
    for n in T["nodes"]: cols[n["col"]].append(n)
    pos = {n["id"]: (c, i - (len(v) - 1) / 2) for c, v in cols.items() for i, n in enumerate(v)}
    col = lambda s: "#b3412e" if s in ("Rejected", "Suspended", "Expired") else "#c98a2b" if s in ("Quarantine", "Conditional", "In progress", "Planned") else "#4f7a4a"
    fig = go.Figure()
    for a, b, lbl in T["edges"]:
        (x0, y0), (x1, y1) = pos[a], pos[b]
        fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", line=dict(color="#c9b9a6", width=1.6), hoverinfo="skip", showlegend=False))
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=str(lbl), showarrow=False, font=dict(size=10, color="#8a7968"), bgcolor="#ffffff")
    fig.add_trace(go.Scatter(x=[pos[n["id"]][0] for n in T["nodes"]], y=[pos[n["id"]][1] for n in T["nodes"]], mode="markers+text",
                             text=[f"<b>{n['label']}</b><br>{(n['sub'] or '')[:24]}" for n in T["nodes"]], textfont=dict(size=10),
                             marker=dict(size=64, symbol="square", color="#ffffff", line=dict(color=[col(n["status"]) for n in T["nodes"]], width=[5 if n["id"] == T["q"] else 2 for n in T["nodes"]])),
                             hovertext=[f"{n['id']}: {n['status']}" for n in T["nodes"]], hoverinfo="text", showlegend=False))
    for i, t in enumerate(["Supplier", "Raw-material lot", "Production order", "Finished batch"]): fig.add_annotation(x=i, y=1, yref="paper", yshift=14, text=t, showarrow=False, font=dict(size=11, color="#a47148"))
    h = max(len(v) for v in cols.values())
    fig.update_layout(height=max(320, 120 * h + 120), xaxis=dict(visible=False, range=[-.5, 3.5]), yaxis=dict(visible=False), **PX)
    st.plotly_chart(fig, width="stretch", key="sp_graph")
    st.caption("Order-level genealogy: every lot consumed by an order is linked to all batches of that order. Red outline = rejected, expired or suspended.")


def page_sp():
    E, M, T = F["expiry"], F["material"], F["trace"]
    sub = st.segmented_control("Section", SUBS, default="Inventory & expiry", key="sp_sub") or "Inventory & expiry"
    mats = {m["api"]: m["api_name"] for m in M["materials"]}
    if sub == "Inventory & expiry":
        m = st.columns(3); m[0].metric("Near-expiry stock", f"{E['near_qty']} kg"); m[1].metric("Projected wastage", inr(E["wastage_value"])); m[2].metric("Expired write-off", inr(E["expired_value"]))
        L = E["lots"]; cmap = {"Expired": "#b3412e", "Near expiry": "#c98a2b", "OK": "#4f7a4a"}
        fig = go.Figure(go.Bar(x=[l["days"] for l in L], y=[l["id"] for l in L], orientation="h", marker_color=["#7a2a1d" if l["status"] == "Rejected" else cmap[l["expiry_status"]] for l in L],
                               text=[f"{l['remaining']} kg | {l['status']}" for l in L], textposition="outside", hovertext=[l["exp_date"] for l in L]))
        fig.add_vline(x=0, line_color="#2b2118"); fig.add_vline(x=60, line=dict(color="#c98a2b", dash="dot"), annotation_text="60-day near-expiry")
        fig.update_layout(height=380, title="Days to expiry by lot (negative = expired)", yaxis=dict(autorange="reversed"), **PX); st.plotly_chart(fig, width="stretch", key="sp_exp")
        df = pd.DataFrame([dict(Lot=l["id"], Material=mats[l["api"]], Supplier=l["sup"], Remaining_kg=l["remaining"], Expiry=l["exp_date"], Days=l["days"], Quality=l["status"], Expiry_status=l["expiry_status"], FEFO_use_kg=l["alloc_kg"] or 0, Stock_value_INR=l["value"]) for l in L])
        st.dataframe(df, width="stretch", hide_index=True)
        pick = st.selectbox("Inspect lot", [l["id"] for l in L], key="sp_lot"); l = next(x for x in L if x["id"] == pick)
        st.markdown(f"**{l['id']}** {badge(l['status'])} {badge(l['expiry_status'])}: {l['remaining']} kg of {l['recv']} kg left, expires {l['exp_date']}, storage {l['storage']}, CoA {l.get('coa_ref', '-')}, QC release {l.get('qc_release_date') or 'pending'}.")
        st.markdown(f"Recommended consumption: **{l['alloc_kg'] or 0} kg**" + ("" if l["usable"] else f" (excluded: {agents.exclusion_reason(l)})"))
        st.button("Trace this lot to finished batches", on_click=goto, args=("Supply & Traceability", "Batch traceability"), kwargs=dict(tq=l["id"]), key="sp_trace_lot")
    elif sub == "Suppliers":
        S = M["suppliers"]; months = ["May", "Jun", "Jul", "Aug", "Sep", "Oct"]
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            for s in S: fig.add_trace(go.Scatter(x=months, y=[v * 100 for v in s["hist"]], mode="lines+markers", name=s["id"]))
            fig.update_layout(height=330, title="On-time delivery (%), last 6 months", colorway=["#6b4a2f", "#a47148", "#4f7a4a", "#c98a2b", "#8a7968"], **PX); st.plotly_chart(fig, width="stretch", key="sp_hist")
        with c2:
            st.dataframe(pd.DataFrame([dict(Supplier=f"{s['id']} {s['name']}", City=s["city"], Risk=s["risk"], Level=s["level"], On_time_pct=round(s["on_time"] * 100), Rejection_pct=round(s["rej"] * 100, 1), Qualification=s["audit"], PO_delay_days=s["delay_days"]) for s in S]),
                         width="stretch", hide_index=True, column_config={"Risk": st.column_config.ProgressColumn(min_value=0, max_value=100)})
        st.caption("Supplier history informs ranking only. Every received lot still enters quarantine and requires incoming inspection and QC release.")
        if not M["ranking"]: st.info("No shortage in this scenario, so no sourcing ranking is needed.")
        for api, rk in M["ranking"].items():
            sh = next(s for s in M["shortages"] if s["api"] == api)
            st.markdown(f"#### Budget-aware ranking: {mats[api]} (shortfall {sh['shortfall']} kg, budget {inr(BUDGET)})")
            st.dataframe(pd.DataFrame([dict(Rank=i + 1, Supplier=f"{r['sup']} {r['name']}", Qualification=r["audit"], Order_kg=r["qty_order"], Price_INR_kg=r["price"], Cost_INR=r["cost"], Coverage_pct=round(r["coverage"] * 100), Lead_days=r["lead"], Score=r["total"], Within_budget=r["within_budget"]) for i, r in enumerate(rk)]),
                         width="stretch", hide_index=True, column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100)})
            for r in rk:
                with st.expander(f"Why {r['sup']} scored {r['total']}"):
                    st.caption(" | ".join(f"{k} {v} x {r['weights'][k]}" for k, v in r["comp"].items()))
                    for x in r["reasons"]: st.markdown(f"- {x}")
    elif sub == "FEFO allocation":
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### FEFO allocation (earliest expiry first, released and unexpired only)")
            st.dataframe(pd.DataFrame([dict(Material=a["api"], Lot=a["lot"], Allocate_kg=a["kg"], Expiry=a["exp_date"], Days=a["days"]) for a in E["allocations"]]), width="stretch", hide_index=True)
        with c2:
            st.markdown("#### Excluded from production")
            for e in E["excluded"]: st.markdown(f"{badge('blocked')} **{e['lot']}** {e['kg']} kg: {e['reason']}")
            if not E["excluded"]: st.caption("None")
            st.markdown("#### Projected wastage")
            for w in E["wastage"]: st.markdown(f"**{w['lot']}**: {w['kg']} kg, {inr(w['value'])} (expires in {w['days']} d)")
            if not E["wastage"]: st.caption("No near-expiry stock left unallocated.")
    elif sub == "Production impact":
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Production orders at risk")
            for o in T["delayed_orders"]: st.markdown(f"{badge('Medium')} **{o['order']}** planned {o['date']}: shortfall {o['shortfall_kg']} kg, about {o['delay_days_if_unmitigated']} days delay if unmitigated")
            if not T["delayed_orders"]: st.caption("No planned order at risk.")
        with c2:
            st.markdown("#### Batches exposed to rejected lots")
            for a in T["affected"]:
                st.markdown(f"**{a['lot']}** to {a['order']} ({a['kg']} kg): {', '.join(a['batches']) or a['state']}")
                for b in a["batches"]: st.button(f"Trace {b}", key=f"pi_{a['lot']}_{b}", on_click=goto, args=("Supply & Traceability", "Batch traceability"), kwargs=dict(tq=b))
            if not T["affected"]: st.caption("No rejected lots in this scenario.")
    else:
        st.session_state.setdefault("tq", "")
        ids = [l["id"] for l in E["lots"]] + [b["id"] for b in mk_state(dict(scenario=SC))["batches"]]
        st.text_input("Lot or batch ID", key="tq", placeholder="e.g. L-AZI-102 or B-AZI-2402A")
        st.caption("Quick pick: " + " | ".join(ids))
        if st.session_state["tq"].strip(): genealogy(agents.search(mk_state(dict(scenario=SC, budget=BUDGET, weeks=WEEKS)), st.session_state["tq"]))
        else: st.info("Search a raw-material lot (forward trace to finished batches) or a finished batch (backward trace to lots and suppliers).")


# ------------------------------------------------------------------ Decisions & Audit
def rec_card(r):
    P, R, rid = r["payload"], r["payload"]["recovery"], r["id"]
    with st.container(border=True):
        st.markdown(f"#### {rid} &nbsp; {badge(r['guard_status'])} &nbsp; {data.SCENARIOS[r['scenario']][0]} &nbsp; ({inr(R['total_cost'])} of {inr(R['budget'])})")
        st.progress(min(1.0, R["total_cost"] / R["budget"]) if R["budget"] else 0)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Prioritised actions**")
            for a in R["actions"]: st.markdown(f"P{a['p']}. {a['text']}")
            if not R["actions"]: st.caption("None")
            st.markdown("**Quality validation**")
            for c in P["guard"]["checks"]: st.markdown(f"{badge(c['result'])} {c['check']}: {c['detail']}")
            for b in P["guard"]["blocked"]: st.markdown(f"{badge('blocked')} {b['action']}: {b['reason']}")
        with c2:
            st.markdown("**Plan comparison**")
            for api, x in R["plans"].items():
                st.dataframe(pd.DataFrame([dict(Plan=p["id"] + (" (chosen)" if p["id"] == x["chosen"] else ""), Option=p["label"], Coverage_pct=round(p["coverage"] * 100), Cost_INR=p["cost"], Within_budget=p["within_budget"]) for p in x["plans"]]), width="stretch", hide_index=True)
                st.caption(" | ".join(x["why"]))
            if not R["plans"]: st.caption("No procurement needed.")
        st.caption("Rule-based agents: every number and check is a deterministic calculation.")
        for i, d in enumerate(R["drafts"]):
            with st.expander(f"Supplier email {i + 1}: {d['supplier_id']} (sent only after approval; editable)", expanded=True):
                st.text_input("To", d["to"], key=f"em_{rid}_{i}_to"); st.text_input("Subject", d["subject"], key=f"em_{rid}_{i}_sub"); st.text_area("Body", d["body"], height=220, key=f"em_{rid}_{i}_body")
        approve_decision_widgets(r, "da", with_emails=True)


def page_da():
    show_flash()
    all_recs = recs(); pend = [r for r in all_recs if r["status"] in ("pending", "revision_requested")]
    st.subheader("Pending approvals")
    for r in pend: rec_card(r)
    if not pend: st.info("Nothing pending. Start the agents in the Agent Workspace.")
    t1, t2, t3, t4, t5 = st.tabs(["Decided", "Email delivery", "Notification history", "Settings and data", "Audit trail"])
    with t1:
        for r in [r for r in all_recs if r not in pend]: st.markdown(f"**{r['id']}** {data.SCENARIOS[r['scenario']][0]} {badge(r['status'])} {r['exec_status'] or ''}  \n{r['comment'] or ''}")
        if len(pend) == len(all_recs): st.caption("None yet.")
    with t2:
        em = store.q("SELECT * FROM emails ORDER BY id DESC LIMIT 100")
        if em:
            st.dataframe(pd.DataFrame([dict(ID=e["id"], Kind=e["kind"], Rec=e["rec_id"], To=e["to_addr"], Status=e["status"], Tries=e["attempts"], Error=e["error"] or "", Time=e["last_ts"]) for e in em]), width="stretch", hide_index=True)
            for e in [e for e in em if e["status"] == "failed"][:10]:
                st.button(f"Retry email #{e['id']} ({e['kind']} to {e['to_addr']})", key=f"rt_{e['id']}", on_click=lambda i=e["id"]: (store.audit("email_retry", "reviewer", None, None, "requested", f"email #{i}"), store.deliver(i)))
        else: st.caption("No emails yet.")
    with t3:
        for n in nf: st.markdown(f"{badge(n['sev'])} `{n['ts']}` **{n['kind'].replace('_', ' ')}** {n['msg']} {'' if n['read'] else '(unread)'}")
    with t4:
        c = store.smtp_cfg()
        st.markdown("SMTP is " + ("configured." if c["configured"] else ":red[not configured]: emails are recorded as failed.") + " Credentials are best kept in .env.")
        with st.form("settings"):
            rev = st.text_input("Reviewer email", store.setting("reviewer_email"))
            a, b = st.columns(2); host = a.text_input("SMTP host", c["host"]); port = b.text_input("Port", str(c["port"]))
            user = a.text_input("SMTP user", c["user"]); pw = b.text_input("SMTP password (not shown)", type="password")
            frm = a.text_input("From address", c["sender"]); sec = b.selectbox("Security", ["starttls", "ssl", "none"], index=["starttls", "ssl", "none"].index(c["security"]) if c["security"] in ("starttls", "ssl", "none") else 0)
            if st.form_submit_button("Save settings"):
                for k, v in dict(reviewer_email=rev, smtp_host=host, smtp_port=port, smtp_user=user, smtp_from=frm, smtp_security=sec).items(): store.set_setting(k, v.strip())
                if pw: store.set_setting("smtp_password", pw)
                store.audit("settings_changed", "reviewer", None, None, "ok", "reviewer/SMTP settings updated"); st.rerun()
        if st.button("Send test to reviewer"):
            row = store.queue_email(None, "test", store.setting("reviewer_email"), "[MedChain] SMTP test", "SMTP configuration test from MedChain AI.")
            st.success("Test email accepted by the SMTP server.") if row["status"] == "sent" else st.error(f"Test email failed: {row['error']}")
        st.markdown("##### Demand data (CSV upload)")
        st.caption("Columns medicine_id,demand_k (weekly, oldest first, 6+ rows per medicine; IDs MED-PCM500, MED-AZI500, MED-MET500). " + (f"Custom data active for {', '.join(sorted(data.OVERRIDE))}." if data.OVERRIDE else "Bundled data active."))
        up = st.file_uploader("Demand CSV", type="csv", key="up_file")
        u1, u2 = st.columns(2)
        if up and u1.button("Apply uploaded data"):
            code, out = upload_demand(dict(csv=up.getvalue().decode("utf-8-sig"))); st.success("Applied. Agents recalculate now.") if code == 200 else st.error(out["error"])
            if code == 200: st.rerun()
        if u2.button("Restore bundled data"): upload_demand(dict(reset=1)); st.rerun()
        st.markdown("##### Bundled datasets (fixed, synthetic, INR)")
        for x in data.catalog():
            d1, d2, d3 = st.columns([3, 1, 5]); d1.write(x["file"]); d2.write(f"{x['rows']} rows"); d3.caption(x["desc"])
            d1.download_button("Download", open(os.path.join(data.DATASETS, x["file"]), "rb").read(), x["file"], "text/csv", key="dl_" + x["file"])
        st.download_button("Example demand upload (surge)", open(os.path.join(store.ROOT, "uploads_examples", "demand_upload_example_surge.csv"), "rb").read(), "demand_upload_example_surge.csv", "text/csv", key="dl_example")
    with t5:
        f1, f2, f3 = st.columns(3); fr = f1.text_input("Recommendation ID", key="af_r"); fs = f2.text_input("Supplier ID", key="af_s"); ft = f3.text_input("Event type", key="af_t")
        w, a_ = [], []
        for v, col in ((fr, "rec_id"), (ft, "event_type"), (fs, "supplier_id")):
            if v: w.append(f"{col}=?"); a_.append(v.strip())
        au = store.q("SELECT * FROM audit" + (" WHERE " + " AND ".join(w) if w else "") + " ORDER BY id DESC LIMIT 300", a_)
        st.dataframe(pd.DataFrame(au).rename(columns=dict(ts="Timestamp", event_type="Event type", actor="Actor", rec_id="Rec ID", supplier_id="Supplier", outcome="Outcome", detail="Detail")).drop(columns=["id"], errors="ignore") if au else pd.DataFrame(), width="stretch", hide_index=True)


{"Command Center": page_cc, "Agent Workspace": page_ws, "Supply & Traceability": page_sp, "Decisions & Audit": page_da}[st.session_state["nav"]]()
