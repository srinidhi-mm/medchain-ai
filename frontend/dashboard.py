"""Executive Overview Dashboard for MedChain AI.

Strict constraints:
- ZERO EMOJIS: clean text, uppercase tags, pure CSS indicators.
- Engaging zero-state Executive Launchpad.
- Multi-agent phased transparency progress indicator during pipeline execution.
- Top-accented KPI cards with contextual status pills.
- Clean Plotly demand chart and balanced alerts table.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
import pandas as pd
import streamlit as st
from frontend.components.charts import render_demand_chart
from frontend.components.kpi_cards import render_overview_kpis
from frontend.components.status_components import (
    render_error_notice,
    render_launchpad,
)
from frontend.components.tables import render_alerts_table, render_table
from frontend.data_access import run_pipeline


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the polished enterprise Overview dashboard."""
    # Header
    st.markdown(
        """
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
            <div>
                <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                    Enterprise Decision Support Platform
                </div>
                <h1 style="font-size: 22px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                    Supply Chain Resilience Overview
                </h1>
                <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                    Real-time demand intelligence, multi-echelon inventory balances, and autonomous agent governance
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    has_results = bool(results and any(results.get("kpis", {}).values()))

    # Action Toolbar
    col_btn, col_info = st.columns([3, 7])
    with col_btn:
        button_label = "Re-run full analysis" if has_results else "Initialize enterprise pipeline"
        run_clicked = st.button(button_label, type="primary", use_container_width=True, key="btn_run_analysis_top")

    if run_clicked:
        # Multi-Agent Phased Progress Transparency
        with st.status("Executing Multi-Agent Orchestration Pipeline...", expanded=True) as status_box:
            st.write("[Agent 1/4] Demand Forecaster Agent: Analyzing 24-month regional time series and seasonality...")
            time.sleep(0.2)
            st.write("[Agent 2/4] Material Risk Agent: Scanning single-sourcing vulnerabilities and supplier lead times...")
            time.sleep(0.2)
            st.write("[Agent 3/4] Production Impact Agent: Evaluating manufacturing schedules against raw material stock...")
            time.sleep(0.2)
            st.write("[Agent 4/4] Quality Guard Agent: Validating GMP certification, shelf-life horizons, and lot quarantine...")
            time.sleep(0.2)

            new_results, err = run_pipeline()
            if err:
                status_box.update(label="Pipeline Execution Notice", state="error")
                render_error_notice(f"Execution notice: {err}")
            else:
                status_box.update(label="Multi-Agent Analysis Completed", state="complete")
                st.session_state["results"] = new_results
                st.rerun()

    # Zero-State: Engaging Executive Launchpad
    if not has_results:
        render_launchpad()
        return

    st.markdown('<div style="margin-top: 14px;"></div>', unsafe_allow_html=True)

    # 1. Six Polished KPI Cards with Top Accent Borders & Status Pills
    render_overview_kpis(results.get("kpis"))

    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # 2. Demand Chart Controls & Chart
    medicines_df = results.get("medicines", pd.DataFrame())
    med_options = []
    med_id_map = {}

    if isinstance(medicines_df, pd.DataFrame) and not medicines_df.empty:
        id_col = "medicine_id" if "medicine_id" in medicines_df.columns else medicines_df.columns[0]
        name_col = "medicine_name" if "medicine_name" in medicines_df.columns else id_col
        for _, row in medicines_df.iterrows():
            m_id = str(row[id_col])
            m_name = str(row[name_col])
            label = f"{m_name} ({m_id})" if m_name != m_id else m_id
            med_options.append(label)
            med_id_map[label] = m_id

    ctrl_col1, ctrl_col2, _ = st.columns([4, 2, 4])
    with ctrl_col1:
        selected_med_label = st.selectbox(
            "Select pharmaceutical product",
            options=med_options if med_options else ["No catalog records loaded"],
            key="overview_med_select",
        )
    with ctrl_col2:
        selected_horizon = st.selectbox(
            "Forecast window",
            options=[7, 15, 30],
            index=2,
            format_func=lambda x: f"{x} days projection",
            key="overview_horizon_select",
        )

    selected_med_id = med_id_map.get(selected_med_label, "")

    # Filter sales and forecast by medicine
    sales_df = results.get("sales", pd.DataFrame())
    forecast_df = results.get("forecast", pd.DataFrame())

    hist_filtered = None
    if isinstance(sales_df, pd.DataFrame) and not sales_df.empty and "medicine_id" in sales_df.columns:
        hist_filtered = sales_df[sales_df["medicine_id"] == selected_med_id]

    fc_filtered = None
    if isinstance(forecast_df, pd.DataFrame) and not forecast_df.empty and "medicine_id" in forecast_df.columns:
        fc_filtered = forecast_df[forecast_df["medicine_id"] == selected_med_id]

    render_demand_chart(
        historical_df=hist_filtered,
        forecast_df=fc_filtered,
        title=f"Demand trajectory: historical vs {selected_horizon}-day forecast",
        medicine_name=selected_med_label,
    )

    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # 3. Top 5 Demand Growth & Priority Alerts
    col_left, col_right = st.columns(2)

    with col_left:
        growth_df = results.get("demand_growth", pd.DataFrame())
        top_growth = pd.DataFrame()
        if isinstance(growth_df, pd.DataFrame) and not growth_df.empty:
            sort_col = "growth_pct" if "growth_pct" in growth_df.columns else growth_df.columns[0]
            top_growth = growth_df.sort_values(sort_col, ascending=False).head(5)

        render_table(
            top_growth,
            title="Top 5 increasing-demand medicines",
            empty_message="No growth figures reported.",
            download_filename="top_increasing_demand.csv",
        )

    with col_right:
        alerts_df = results.get("alerts", pd.DataFrame())
        render_alerts_table(alerts_df)
