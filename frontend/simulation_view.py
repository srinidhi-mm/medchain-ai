"""Disruption Simulation view for MedChain AI.

Features:
- Scenario stress-testing: Demand spike, Supplier delay, Material shortage, Capacity reduction.
- Dynamic target selector based on selected scenario and severity slider.
- Before-and-after impact comparison table and recovery recommendations.
- Mandatory hypothetical disclaimer on every result: 'Hypothetical result. Not based on actual events.'
- 'Save for comparison' session state persistence for side-by-side multi-scenario evaluation.
- CSV export for scenario outcomes.
- Dataset integrity guarantee: Raw datasets are never modified.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
from frontend.components.charts import render_simulation_comparison_chart
from frontend.components.status_components import render_empty_state, render_error_notice
from frontend.components.tables import render_table
from frontend.data_access import run_simulation


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the Disruption simulation page."""
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                Resilience Tool
            </div>
            <h1 style="font-size: 20px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                Supply Chain Disruption Stress-Testing Simulator
            </h1>
            <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                In-silico simulation of epidemiological demand spikes, vendor insolvencies, and manufacturing line failures
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Empty state check
    if not results or not any(results.get("kpis", {}).values()):
        render_empty_state("No results yet. Run analysis from Overview.")
        return

    # Initialize saved scenarios in session state if missing
    if "saved_scenarios" not in st.session_state:
        st.session_state["saved_scenarios"] = []

    # 1. Scenario Selection and Controls
    scenarios = [
        "Demand spike",
        "Supplier delay",
        "Material shortage",
        "Capacity reduction",
    ]

    sim_options = results.get("sim_options", {})

    col_scen, col_tgt, col_sev = st.columns([3, 4, 3])
    with col_scen:
        selected_scenario = st.selectbox("Stress-test scenario", options=scenarios, key="sim_scenario_select")

    # Determine targets based on scenario
    available_targets: List[str] = sim_options.get(selected_scenario, [])
    if not available_targets:
        if selected_scenario == "Demand spike":
            meds = results.get("medicines", pd.DataFrame())
            if isinstance(meds, pd.DataFrame) and not meds.empty:
                col_name = "medicine_name" if "medicine_name" in meds.columns else meds.columns[0]
                available_targets = meds[col_name].dropna().tolist()
        elif selected_scenario in ("Supplier delay",):
            supps = results.get("suppliers", pd.DataFrame())
            if isinstance(supps, pd.DataFrame) and not supps.empty:
                col_name = "name" if "name" in supps.columns else supps.columns[0]
                available_targets = supps[col_name].dropna().tolist()
        elif selected_scenario in ("Material shortage",):
            inv = results.get("inventory", pd.DataFrame())
            if isinstance(inv, pd.DataFrame) and not inv.empty:
                col_name = "material" if "material" in inv.columns else inv.columns[0]
                available_targets = inv[col_name].dropna().tolist()
        elif selected_scenario in ("Capacity reduction",):
            sched = results.get("schedule", pd.DataFrame())
            if isinstance(sched, pd.DataFrame) and not sched.empty and "line_id" in sched.columns:
                available_targets = sched["line_id"].dropna().unique().tolist()

    with col_tgt:
        selected_target = st.selectbox(
            "Disruption target parameter",
            options=available_targets if available_targets else ["System-wide baseline"],
            key="sim_target_select",
        )

    with col_sev:
        severity_val = st.slider(
            "Stress-test severity multiplier",
            min_value=0.1,
            max_value=3.0,
            value=1.5,
            step=0.1,
            format="%.1fx",
            key="sim_severity_slider",
        )

    # Simulation Trigger
    run_sim_btn = st.button("Execute disruption simulation", type="primary", use_container_width=True)

    if run_sim_btn:
        with st.spinner(f"Simulating {selected_scenario} on {selected_target} (severity {severity_val}x)..."):
            sim_output, err = run_simulation(
                scenario=selected_scenario,
                target=selected_target,
                severity=severity_val,
            )
            if err:
                render_error_notice(f"Simulation execution notice: {err}")
            elif isinstance(sim_output, dict):
                st.session_state["active_simulation"] = {
                    "scenario": selected_scenario,
                    "target": selected_target,
                    "severity": severity_val,
                    "comparison": sim_output.get("comparison", pd.DataFrame()),
                    "recovery": sim_output.get("recovery", []),
                }
                st.rerun()

    # Active Simulation Results
    active_sim = st.session_state.get("active_simulation")
    if active_sim:
        st.markdown('<div style="margin-top: 24px; border-top: 1px solid #E2E8F0; padding-top: 16px;"></div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px;
                        box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05); padding: 14px 18px; margin-bottom: 16px;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="font-size: 14px; font-weight: 700; color: #0F172A;">
                        Scenario: {active_sim["scenario"]} &nbsp;|&nbsp; Target: {active_sim["target"]} &nbsp;|&nbsp; Multiplier: {active_sim["severity"]}x
                    </div>
                    <div style="background-color: #FEF3C7; color: #92400E; border: 1px solid #FDE68A;
                                border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;">
                        Hypothetical result. Not based on actual events.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        comparison_df = active_sim.get("comparison", pd.DataFrame())
        if not isinstance(comparison_df, pd.DataFrame):
            comparison_df = pd.DataFrame(comparison_df)

        # Before and after impact chart & table
        render_simulation_comparison_chart(comparison_df)

        render_table(
            comparison_df,
            title="Operational impact metrics: baseline vs disruption scenario",
            empty_message="No impact delta metrics calculated.",
            download_filename=f"simulation_{active_sim['scenario'].lower().replace(' ', '_')}.csv",
        )

        # Recovery recommendations
        recovery_items = active_sim.get("recovery", [])
        if recovery_items:
            st.markdown(
                '<div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
                'letter-spacing: 0.04em; margin: 16px 0 8px 0;">Prescribed Autonomous Mitigation Actions</div>',
                unsafe_allow_html=True,
            )
            for r in recovery_items:
                st.markdown(
                    f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
                    f'border-radius: 6px; box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04); '
                    f'padding: 12px 14px; margin-bottom: 6px; font-size: 13px; color: #1E293B; line-height: 1.4;">'
                    f'{r}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Save for comparison action
        st.markdown('<div style="margin-top: 14px;"></div>', unsafe_allow_html=True)
        col_save, _ = st.columns([3, 7])
        with col_save:
            if st.button("Save scenario for comparative review", key="btn_save_sim"):
                scenario_entry = {
                    "name": f"{active_sim['scenario']} ({active_sim['target']}, {active_sim['severity']}x)",
                    "scenario": active_sim["scenario"],
                    "target": active_sim["target"],
                    "severity": active_sim["severity"],
                    "data": comparison_df,
                }
                st.session_state["saved_scenarios"].append(scenario_entry)
                st.success("Scenario saved to session comparative matrix.")
                st.rerun()

    # Saved Scenarios Side-by-Side Comparison
    saved_list = st.session_state.get("saved_scenarios", [])
    if saved_list:
        st.markdown('<div style="margin-top: 36px; border-top: 1px solid #E2E8F0; padding-top: 18px;"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
            'letter-spacing: 0.04em; margin-bottom: 8px;">Saved Scenario Comparison Matrix</div>',
            unsafe_allow_html=True,
        )

        summary_rows = []
        for s in saved_list:
            df_s = s["data"]
            row_dict = {"Scenario description": s["name"], "Severity": f"{s['severity']}x"}
            if isinstance(df_s, pd.DataFrame) and not df_s.empty:
                for _, r in df_s.iterrows():
                    m = r.get("measure", "")
                    val = r.get("scenario", "")
                    if m:
                        row_dict[str(m)] = val
            summary_rows.append(row_dict)

        summary_df = pd.DataFrame(summary_rows)
        render_table(
            summary_df,
            empty_message="No saved scenarios.",
            download_filename="saved_scenarios_comparison.csv",
        )

        if st.button("Clear saved comparison matrix", key="btn_clear_scenarios"):
            st.session_state["saved_scenarios"] = []
            st.rerun()

    # Integrity note
    st.markdown(
        '<div style="font-size: 11px; color: #64748B; margin-top: 20px;">'
        'Dataset safety guarantee: All simulation evaluations execute in memory. Underlying raw database and CSV files remain unmodified.'
        '</div>',
        unsafe_allow_html=True,
    )
