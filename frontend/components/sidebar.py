"""Enterprise Sidebar navigation with structured 5-step workflow stepper.

Strict constraints:
- ZERO EMOJIS or Unicode pictograms.
- Clean numeric step badges (1 to 5).
- Pure CSS status pills (READY, ALERTS, PENDING).
- Fixed left layout with high-contrast active states.
"""

from __future__ import annotations

from typing import Dict, Optional
import streamlit as st
from frontend.data_access import get_results, get_system_status

WORKFLOW_STEPS = [
    {"page": "1. Data and forecast", "num": "1", "label": "Data and forecast", "default_pill": "READY"},
    {"page": "2. Inventory and materials", "num": "2", "label": "Inventory and materials", "default_pill": "READY"},
    {"page": "3. Agent analysis", "num": "3", "label": "Agent analysis", "default_pill": "4 AGENTS"},
    {"page": "4. Procurement and production", "num": "4", "label": "Procurement and production", "default_pill": "OPTIMIZE"},
    {"page": "5. Approval", "num": "5", "label": "Governance and approval", "default_pill": "PENDING"},
]


def render_sidebar() -> str:
    """Render the enterprise sidebar navigation."""
    if "page" not in st.session_state:
        st.session_state["page"] = "Overview"

    current_page = st.session_state["page"]
    results = get_results()

    with st.sidebar:
        # Enterprise Header
        st.markdown(
            """
            <div style="padding-bottom: 14px; border-bottom: 1px solid #E2E8F0; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-size: 19px; font-weight: 800; color: #0F172A; letter-spacing: -0.02em;">MedChain AI</span>
                    <span style="background-color: #EFF6FF; color: #0284C7; border: 1px solid #BFDBFE; border-radius: 4px;
                                 padding: 1px 6px; font-size: 9px; font-weight: 700; letter-spacing: 0.05em;">ENTERPRISE</span>
                </div>
                <div style="font-size: 11px; color: #64748B; line-height: 1.4;">
                    Pharmaceutical demand intelligence and supply chain resilience
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Overview Navigation
        is_overview_active = current_page == "Overview"
        if st.button(
            "Overview Dashboard",
            key="nav_btn_overview",
            type="primary" if is_overview_active else "secondary",
            use_container_width=True,
        ):
            st.session_state["page"] = "Overview"
            st.rerun()

        # Workflow Stepper Group
        st.markdown(
            '<div style="font-size: 10px; font-weight: 700; text-transform: uppercase; '
            'color: #94A3B8; margin: 20px 0 8px 4px; letter-spacing: 0.06em;">Decision Workflow</div>',
            unsafe_allow_html=True,
        )

        for step in WORKFLOW_STEPS:
            p_name = step["page"]
            is_active = current_page == p_name or (p_name.startswith("5.") and current_page == "5. Approval")

            # Determine dynamic pill text based on pipeline status
            pill_text = step["default_pill"]
            if results and "kpis" in results:
                if step["num"] == "2" and (results.get("kpis", {}).get("critical_shortages") or 0) > 0:
                    pill_text = f"{results['kpis']['critical_shortages']} SHORTAGES"
                elif step["num"] == "5":
                    guard_status = results.get("guard", {}).get("status")
                    if guard_status:
                        pill_text = str(guard_status).upper()

            btn_label = f"[{step['num']}]  {step['label']}  ·  {pill_text}"

            if st.button(
                btn_label,
                key=f"nav_step_{step['num']}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state["page"] = p_name if p_name != "5. Governance and approval" else "5. Approval"
                st.rerun()

        # Tools Group
        st.markdown(
            '<div style="font-size: 10px; font-weight: 700; text-transform: uppercase; '
            'color: #94A3B8; margin: 22px 0 8px 4px; letter-spacing: 0.06em;">Resilience Tools</div>',
            unsafe_allow_html=True,
        )

        tool_items = [
            ("Disruption simulation", "Disruption simulation"),
            ("Decision and audit history", "Decision and audit history"),
        ]

        for label, page_key in tool_items:
            is_active = current_page == page_key
            if st.button(
                label,
                key=f"nav_tool_{page_key}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state["page"] = page_key
                st.rerun()

        # System Health & Connectivity
        st.markdown('<div style="margin-top: 36px;"></div>', unsafe_allow_html=True)
        status_info = get_system_status()

        st.markdown(
            f"""
            <div style="padding-top: 14px; border-top: 1px solid #E2E8F0; font-size: 11px; color: #64748B;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <span>Database</span>
                    <span style="display: inline-flex; align-items: center; color: #0F172A; font-weight: 600;">
                        <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background-color: #10B981; margin-right: 5px;"></span>
                        {status_info.get("database_status", "Connected")}
                    </span>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <span>Dataset</span>
                    <span style="display: inline-flex; align-items: center; color: #0F172A; font-weight: 600;">
                        <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background-color: #0284C7; margin-right: 5px;"></span>
                        {status_info.get("data_status", "Synthetic")}
                    </span>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <span>LLM Engine</span>
                    <span style="display: inline-flex; align-items: center; color: #0F172A; font-weight: 600;">
                        <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background-color: #94A3B8; margin-right: 5px;"></span>
                        {status_info.get("llm_status", "Offline")}
                    </span>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span>System Version</span>
                    <span style="color: #0F172A; font-weight: 600;">{status_info.get("version", "1.0.0")}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state["page"]
