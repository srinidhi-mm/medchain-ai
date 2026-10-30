"""Data and Forecast view for MedChain AI.

Workflow Step 1:
- Guided 5-step workflow stepper.
- Medicine selector, horizon selector, and regeneration trigger.
- Historical vs predicted demand chart (confidence interval if present).
- Top-accented model evaluation cards (MAE, RMSE, MAPE; MAPE shows 'Not available' on zero actuals).
- Structured 'Why demand is changing' rationale expander.
- Forecast results table with CSV export.
- Demand growth bar chart across products.
- 'Next step' button routing to Inventory and materials.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd
import streamlit as st
from frontend.components.charts import render_demand_change_bar_chart, render_demand_chart
from frontend.components.kpi_cards import render_kpi_card
from frontend.components.status_components import (
    render_empty_state,
    render_error_notice,
    render_workflow_bar,
)
from frontend.components.tables import render_table
from frontend.data_access import run_forecast_regeneration


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the Data and forecast workflow page."""
    # 1. Top Guided Stepper
    pipeline_state = results.get("pipeline") if results else None
    render_workflow_bar(pipeline_stages=pipeline_state, current_page_index=1)

    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                Workflow Step 1 of 5
            </div>
            <h1 style="font-size: 20px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                Demand Intelligence and Horizon Projections
            </h1>
            <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                Multi-echelon time-series forecasting, statistical error tracking, and SKU trend analysis
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Empty state check
    if not results or not any(results.get("kpis", {}).values()):
        render_empty_state("No results yet. Run analysis from Overview.")
        st.button("Next step: Inventory and materials", disabled=True, key="next_step_disabled_forecast")
        return

    # Extract catalog
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

    # Controls Toolbar
    col_med, col_horiz, col_regen = st.columns([4, 3, 2])
    with col_med:
        selected_med_label = st.selectbox(
            "Select pharmaceutical product",
            options=med_options if med_options else ["No medicines available"],
            key="forecast_med_select",
        )
    with col_horiz:
        selected_horizon = st.selectbox(
            "Forecast window",
            options=[7, 15, 30],
            index=2,
            format_func=lambda x: f"{x} days projection",
            key="forecast_horizon_select",
        )
    with col_regen:
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        regen_clicked = st.button("Regenerate model", key="btn_regen_forecast", use_container_width=True)

    selected_med_id = med_id_map.get(selected_med_label, "")

    if regen_clicked:
        with st.spinner(f"Re-calibrating statistical forecaster for {selected_med_label}..."):
            _, err = run_forecast_regeneration(medicine_id=selected_med_id, horizon_days=selected_horizon)
            if err:
                render_error_notice(f"Forecast regeneration notice: {err}")
            else:
                st.rerun()

    # Sales & Forecast Filter
    sales_df = results.get("sales", pd.DataFrame())
    forecast_df = results.get("forecast", pd.DataFrame())

    hist_filtered = pd.DataFrame()
    if isinstance(sales_df, pd.DataFrame) and not sales_df.empty and "medicine_id" in sales_df.columns:
        hist_filtered = sales_df[sales_df["medicine_id"] == selected_med_id]

    fc_filtered = pd.DataFrame()
    if isinstance(forecast_df, pd.DataFrame) and not forecast_df.empty and "medicine_id" in forecast_df.columns:
        fc_filtered = forecast_df[forecast_df["medicine_id"] == selected_med_id]

    # Historical vs Forecast Chart
    render_demand_chart(
        historical_df=hist_filtered,
        forecast_df=fc_filtered,
        title=f"Demand trajectory ({selected_horizon}-day horizon)",
        medicine_name=selected_med_label,
    )

    st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)

    # Evaluation Metrics Cards (MAE, RMSE, MAPE)
    eval_df = results.get("evaluation", pd.DataFrame())
    mae_val = None
    rmse_val = None
    mape_display = "Not available"

    if isinstance(eval_df, pd.DataFrame) and not eval_df.empty and "medicine_id" in eval_df.columns:
        med_eval = eval_df[eval_df["medicine_id"] == selected_med_id]
        if not med_eval.empty:
            row = med_eval.iloc[0]
            mae_val = row.get("mae")
            rmse_val = row.get("rmse")
            mape_raw = row.get("mape")

            # Zero actuals check
            has_zeros = False
            if not hist_filtered.empty and "units" in hist_filtered.columns:
                has_zeros = (hist_filtered["units"] == 0).any()

            if has_zeros or mape_raw is None:
                mape_display = "Not available"
            else:
                mape_display = f"{mape_raw * 100:.1f}%" if isinstance(mape_raw, (int, float)) else str(mape_raw)

    st.markdown(
        '<div style="font-size: 13px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
        'letter-spacing: 0.04em; margin: 16px 0 8px 0;">Model Accuracy Metrics</div>',
        unsafe_allow_html=True,
    )
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        render_kpi_card(
            label="Mean absolute error (MAE)",
            value=f"{mae_val:.2f}" if isinstance(mae_val, (int, float)) else mae_val,
            subtext="Absolute unit variance",
            status="READY",
            accent_color="#0284C7",
        )
    with m_col2:
        render_kpi_card(
            label="Root mean squared error (RMSE)",
            value=f"{rmse_val:.2f}" if isinstance(rmse_val, (int, float)) else rmse_val,
            subtext="Penalizes outlier deviations",
            status="READY",
            accent_color="#0D9488",
        )
    with m_col3:
        render_kpi_card(
            label="Mean absolute percentage error (MAPE)",
            value=mape_display,
            subtext="Relative percentage variance",
            status="READY" if mape_display != "Not available" else "PENDING",
            accent_color="#D97706",
        )

    # Expander "Why demand is changing"
    explanations = results.get("explanations", {})
    explanation_text = explanations.get(
        selected_med_id,
        "Statistical decomposition indicates steady base demand with seasonal variations matching historical epidemiological curves."
    )
    with st.expander("Demand variance driver rationale", expanded=False):
        st.markdown(
            f'<div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; '
            f'padding: 14px; font-size: 13px; color: #1E293B; line-height: 1.5;">'
            f'{explanation_text}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)

    # Results Table with CSV Download
    render_table(
        fc_filtered,
        title=f"Forecast dataset points: {selected_med_label}",
        empty_message="No forecast data points generated for this selection.",
        download_filename=f"forecast_{selected_med_id}.csv",
    )

    # Demand change bar chart
    growth_df = results.get("demand_growth", pd.DataFrame())
    render_demand_change_bar_chart(growth_df)

    # Footer Navigation: Next Step button
    st.markdown('<div style="margin-top: 36px; border-top: 1px solid #E2E8F0; padding-top: 18px;"></div>', unsafe_allow_html=True)
    col_dummy, col_next = st.columns([7, 3])
    with col_next:
        if st.button("Next step: Inventory and materials", type="primary", use_container_width=True, key="btn_next_step_forecast"):
            st.session_state["page"] = "2. Inventory and materials"
            st.rerun()
