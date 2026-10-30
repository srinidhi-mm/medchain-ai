"""Agent Analysis view for MedChain AI.

Workflow Step 3:
- Guided 5-step workflow stepper.
- Four agent overview cards with top accent borders and status pills.
- Individual agent tabs with findings and recommendations breakdown.
- Quality Guard regulatory validation checks table, status badge, and revision-limited re-run trigger.
- Expanders per major autonomous decision (what, why, supporting data, action, risk).
- Multi-agent communication log expander.
- 'Next step' button routing to Procurement and production.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
from frontend.components.status_components import (
    render_empty_state,
    render_error_notice,
    render_status_pill,
    render_workflow_bar,
)
from frontend.components.tables import render_table
from frontend.data_access import call


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the Agent analysis workflow page."""
    # 1. Top Guided Stepper
    pipeline_state = results.get("pipeline") if results else None
    render_workflow_bar(pipeline_stages=pipeline_state, current_page_index=3)

    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                Workflow Step 3 of 5
            </div>
            <h1 style="font-size: 20px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                Autonomous Multi-Agent Synthesis and Validation
            </h1>
            <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                Collaborative agent swarm assessing lead times, production capacity, and cGMP compliance
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Empty state check
    if not results or not any(results.get("kpis", {}).values()):
        render_empty_state("No results yet. Run analysis from Overview.")
        st.button("Next step: Procurement and production", disabled=True, key="next_step_disabled_agents")
        return

    # Extract agents list
    agents_data: List[Dict[str, Any]] = results.get("agents", [])

    agent_specs = [
        {"name": "Material Risk", "accent": "#0284C7"},
        {"name": "Production Impact", "accent": "#0D9488"},
        {"name": "Recovery Planning", "accent": "#D97706"},
        {"name": "Quality Guard", "accent": "#10B981"},
    ]

    agent_map = {a.get("agent", ""): a for a in agents_data if isinstance(a, dict)}

    # 2. Four Agent Overview Cards
    cols = st.columns(4)
    for idx, spec in enumerate(agent_specs):
        name = spec["name"]
        accent = spec["accent"]
        data = agent_map.get(name, {})
        status = data.get("status", "PENDING")
        purpose = data.get("purpose", "Specialist intelligence domain")
        last_run = data.get("last_run", "Not executed")
        findings_count = len(data.get("findings", []))
        recs_count = len(data.get("recommendations", []))

        with cols[idx]:
            pill_html = render_status_pill(status)
            st.markdown(
                f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-top: 3px solid {accent}; '
                f'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05); '
                f'padding: 16px; margin-bottom: 16px; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">'
                f'<div>'
                f'<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">'
                f'<span style="font-size: 13px; font-weight: 700; color: #0F172A;">{name} Agent</span>'
                f'{pill_html}'
                f'</div>'
                f'<div style="font-size: 12px; color: #64748B; margin-bottom: 12px; line-height: 1.4;">{purpose}</div>'
                f'</div>'
                f'<div style="border-top: 1px solid #F1F5F9; padding-top: 10px; font-size: 11px; color: #64748B;">'
                f'<div style="display: flex; justify-content: space-between; margin-bottom: 3px;">'
                f'<span>Last execution</span><span style="color: #0F172A; font-weight: 600;">{last_run}</span>'
                f'</div>'
                f'<div style="display: flex; justify-content: space-between; margin-bottom: 3px;">'
                f'<span>Findings</span><span style="color: #0F172A; font-weight: 600;">{findings_count}</span>'
                f'</div>'
                f'<div style="display: flex; justify-content: space-between;">'
                f'<span>Recommendations</span><span style="color: #0F172A; font-weight: 600;">{recs_count}</span>'
                f'</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)

    # 3. Agent Tabs
    tab_names = [f"{spec['name']} Agent" for spec in agent_specs]
    tabs = st.tabs(tab_names)

    for idx, spec in enumerate(agent_specs):
        name = spec["name"]
        with tabs[idx]:
            agent_info = agent_map.get(name, {})
            findings = agent_info.get("findings", [])
            recommendations = agent_info.get("recommendations", [])

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(
                    '<div style="font-size: 13px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
                    'letter-spacing: 0.04em; margin-bottom: 10px;">Findings and Risk Factors</div>',
                    unsafe_allow_html=True,
                )
                if findings:
                    for f in findings:
                        st.markdown(
                            f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
                            f'border-radius: 6px; box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04); '
                            f'padding: 12px 14px; margin-bottom: 8px; font-size: 13px; color: #1E293B; line-height: 1.4;">'
                            f'{f}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown('<p style="font-size: 13px; color: #64748B;">No critical findings reported by this agent.</p>', unsafe_allow_html=True)

            with c2:
                st.markdown(
                    '<div style="font-size: 13px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
                    'letter-spacing: 0.04em; margin-bottom: 10px;">Actionable Mitigation Directives</div>',
                    unsafe_allow_html=True,
                )
                if recommendations:
                    for r in recommendations:
                        st.markdown(
                            f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
                            f'border-radius: 6px; box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04); '
                            f'padding: 12px 14px; margin-bottom: 8px; font-size: 13px; color: #1E293B; line-height: 1.4;">'
                            f'{r}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown('<p style="font-size: 13px; color: #64748B;">No prescriptive recommendations submitted.</p>', unsafe_allow_html=True)

            # Quality Guard Regulatory Section
            if name == "Quality Guard":
                st.markdown('<div style="margin-top: 24px; border-top: 1px solid #E2E8F0; padding-top: 16px;"></div>', unsafe_allow_html=True)
                guard_info = results.get("guard", {})
                guard_status = guard_info.get("status", "PENDING")
                rev_count = guard_info.get("revision", 0)
                max_rev = guard_info.get("max_revision", 3)
                checks_df = guard_info.get("checks", pd.DataFrame())

                q_col1, q_col2 = st.columns([7, 3])
                with q_col1:
                    status_badge = render_status_pill(guard_status)
                    st.markdown(
                        f'<div style="font-size: 14px; color: #0F172A; font-weight: 600;">'
                        f'Regulatory verification status: {status_badge} &nbsp;|&nbsp; Revision cycle: {rev_count} / {max_rev}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with q_col2:
                    is_at_limit = rev_count >= max_rev
                    re_run_btn = st.button(
                        "Re-run verification",
                        disabled=is_at_limit,
                        use_container_width=True,
                        key="btn_rerun_guard",
                    )
                    if is_at_limit:
                        st.caption("Maximum revision cycles reached.")

                if re_run_btn:
                    with st.spinner("Re-executing Quality Guard regulatory checks..."):
                        _, err = call("run_pipeline")
                        if err:
                            render_error_notice(f"Validation re-run notice: {err}")
                        else:
                            st.rerun()

                render_table(
                    checks_df,
                    title="cGMP compliance and regulatory verification checklist",
                    empty_message="No compliance checks evaluated.",
                    download_filename="quality_guard_checks.csv",
                )

    st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)

    # 4. Major Autonomous Decisions
    decisions = results.get("decisions", [])
    st.markdown(
        '<div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
        'letter-spacing: 0.04em; margin: 16px 0 8px 0;">Autonomous Agent Decision Rationale</div>',
        unsafe_allow_html=True,
    )

    if decisions:
        for idx, dec in enumerate(decisions):
            title = dec.get("title", f"Decision {idx + 1}")
            with st.expander(title, expanded=False):
                st.markdown(f"**Directive**: {dec.get('what', 'Not specified')}")
                st.markdown(f"**Underlying reasoning**: {dec.get('why', 'Not specified')}")
                st.markdown(f"**Supporting evidence**: {dec.get('data', 'Not specified')}")
                st.markdown(f"**Prescribed action**: {dec.get('action', 'Not specified')}")
                st.markdown(f"**Risk exposure if ignored**: {dec.get('risk', 'Not specified')}")
    else:
        st.markdown(
            '<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
            'border-radius: 8px; padding: 18px; color: #64748B; font-size: 13px;">'
            'No major autonomous decisions logged for this run.'
            '</div>',
            unsafe_allow_html=True,
        )

    # 5. Multi-Agent Communication Log
    log_df = results.get("log", pd.DataFrame())
    with st.expander("Inter-agent communication and trace audit log", expanded=False):
        render_table(
            log_df,
            empty_message="No inter-agent messages recorded.",
            download_filename="agent_communication_log.csv",
        )

    # Footer Navigation: Next Step button
    st.markdown('<div style="margin-top: 36px; border-top: 1px solid #E2E8F0; padding-top: 18px;"></div>', unsafe_allow_html=True)
    col_dummy, col_next = st.columns([7, 3])
    with col_next:
        if st.button("Next step: Procurement and production", type="primary", use_container_width=True, key="btn_next_step_agents"):
            st.session_state["page"] = "4. Procurement and production"
            st.rerun()
