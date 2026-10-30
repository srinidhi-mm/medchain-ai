# MedChain AI (medchain-ai-claude)

Multi-agent pharmaceutical supply-chain resilience platform (Indian synthetic dataset, INR).
The agents, data layer, email and audit code use only the Python standard library. The Streamlit UI adds streamlit, plotly and pandas.

## Run (two interchangeable UIs, same agents, data, database and approval logic)
**A. Streamlit + Plotly (recommended)**

    pip install -r requirements.txt
    streamlit run streamlit_app.py          # opens http://localhost:8501
    (Windows: run_streamlit.bat   |   macOS/Linux: ./run_streamlit.sh)

**B. Zero-dependency version** (Python 3.9+ standard library only)

    python server.py            # Windows: py server.py
    open http://localhost:8000

Both UIs share `data/medchain.db`; run one at a time.

## What is real
- Six agents (Demand, Material Risk, Expiry/FEFO, Production & Traceability, Recovery, Quality Guard)
  run in an orchestrator over shared findings. Each agent reads upstream handoffs and emits structured
  output; the Agent Workspace shows the actual backend event stream (status, inputs, messages, outputs).
- All numbers are deterministic calculations (rule-based; no LLM and no external AI API). Same scenario + budget + horizon = same result.
- Changing scenario / budget / horizon recalculates every agent output and the recommendation.
- Budget-aware supplier ranking: weighted score (price .25, reliability .20, quality .20, lead time .15,
  capacity fit .10, budget fit .10), INR cost, MOQ/capacity fit, explainable "why" per supplier.
- Plans compared per shortage: single source, dual source, budget-capped + reschedule, or reschedule only.
- Supplier history is a ranking input only. Every RFQ states that new lots go to quarantine and need
  incoming inspection and QC release; the Quality Guard never treats history as release.
- Expired, rejected and quarantined lots are never allocated. Suspended suppliers are excluded.
- Nothing external happens without approval. Approval sends an RFQ email (not a purchase order).
  REVIEW plans need a reviewer comment; BLOCKED plans cannot be approved.

## Email
1. Copy `.env.example` to `.env` and fill SMTP values (Gmail needs an app password), or use Decisions & Audit > Settings.
2. Set the reviewer email in Settings. A reviewer alert is sent when a run has critical items or needs review.
3. Supplier emails are editable per recommendation and sent only on Approve.
4. Status is "sent" only when the SMTP server accepts the message; otherwise "failed" with the error,
   a Retry button, a notification and an audit record. Without SMTP config, emails are recorded as failed.
   Note: settings saved in the UI (including SMTP password) are stored in data/medchain.db; prefer .env.

## Demo flow
Pick "5. Combined Disruption" > Agent Workspace > Start agent workflow > watch agents > Approve (comment required)
> Decisions & Audit shows email status, retry and audit rows. Compare scenarios and budgets (try 500000 vs 1500000).
Traceability: Supply & Traceability > Batch traceability > L-AZI-102 (use the Quality Rejection scenario for red status).

## Datasets (datasets/, all synthetic, fixed, INR)
medicines, apis, suppliers, supplier_apis (price/capacity/MOQ/lead), supplier_history (6 months on-time, inspection reject %),
raw_material_lots (expiry, QC status, CoA), production_orders, finished_batches, material_consumption, purchase_orders,
demand_weekly (26 weeks; agents use the latest 12), api_price_history_inr (12 months), scenarios, scenario_overrides.
The CSVs are the source of truth: edit a file and restart to change the data. `scenario_overrides.csv` lists the exact
changes each scenario applies, so scenarios stay deterministic. The app lists and downloads them under Decisions & Audit > Settings.
Names, cities and emails are fictional (`.example` domains). Prices are illustrative, not market quotes.

## Tests
    python -m unittest discover -s tests

## Layout
    streamlit_app.py   Streamlit + Plotly UI (4 sections)
    .streamlit/        theme (white, beige, brown)
    requirements.txt   streamlit, plotly, pandas
    app/service.py     run/approval/execution logic shared by both UIs
    server.py          HTTP API + orchestration runner + approval/execution
    datasets/          fixed CSV dataset (see above)
    uploads_examples/  example demand CSV to try the upload (shows a surge)
    tests/             standard-library unit tests
    app/data.py        CSV loader + scenario overrides
    app/agents.py      agents, orchestrator, supplier ranking, traceability
    app/store.py       SQLite, audit, notifications, SMTP delivery
    static/index.html  UI for the zero-dependency server (4 sections)
    data/medchain.db   created on first run (delete to reset)

## Optional extras
- CSV demand upload: Decisions & Audit > Settings (try `uploads_examples/demand_upload_example_surge.csv`). Columns `medicine_id,demand_k` (or `demand_k_tablets`), oldest first, 6+ rows per medicine. Scenarios still apply on top of uploaded data. Upload is held in memory (reset on restart); the latest 12 weeks are used.

## Notes
All data is synthetic and fixed. The app recalculates on every change, but it does not pull live market feeds.

- Changing scenario, budget, horizon or uploading data reruns the agents at once (the Agent Workspace restarts the workflow if it is open).
- Email delivery was not tested against a live SMTP server in the build sandbox: add SMTP details to `.env` and use "Send test to reviewer".
- Recommendation IDs continue after restarts (REC-0001, REC-0002, ...) so earlier decisions and audit rows are never overwritten.

- Streamlit live view: the workspace polls the running agents every 0.6 s while a run is active and stops when it finishes. Event history stays on screen.
- Streamlit keeps the run view per browser session; recommendations, emails and audit persist in SQLite.

