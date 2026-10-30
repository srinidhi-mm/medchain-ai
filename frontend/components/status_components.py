"""Enterprise status indicators, workflow stepper, and zero-state launchpad.

Strict constraints:
- ZERO EMOJIS, Unicode pictograms, or decorative symbols.
- Pure CSS status dots, tinted status pills, and subtle elevation (box-shadow).
- Enterprise palette: Deep Navy Slate #0F172A, Primary Blue #0284C7, Emerald #10B981,
  Amber #D97706, Critical Crimson #DC2626, Border #E2E8F0.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import streamlit as st

# Enterprise Color Map
STATUS_CONFIG = {
    "COMPLETED": {"bg": "#ECFDF5", "text": "#065F46", "dot": "#10B981", "border": "#A7F3D0"},
    "OPTIMAL": {"bg": "#ECFDF5", "text": "#065F46", "dot": "#10B981", "border": "#A7F3D0"},
    "VALIDATED": {"bg": "#ECFDF5", "text": "#065F46", "dot": "#10B981", "border": "#A7F3D0"},
    "APPROVED": {"bg": "#ECFDF5", "text": "#065F46", "dot": "#10B981", "border": "#A7F3D0"},
    "ACTIVE": {"bg": "#EFF6FF", "text": "#1E40AF", "dot": "#0284C7", "border": "#BFDBFE"},
    "RUNNING": {"bg": "#EFF6FF", "text": "#1E40AF", "dot": "#0284C7", "border": "#BFDBFE"},
    "READY": {"bg": "#EFF6FF", "text": "#1E40AF", "dot": "#0284C7", "border": "#BFDBFE"},
    "LOW": {"bg": "#ECFDF5", "text": "#065F46", "dot": "#10B981", "border": "#A7F3D0"},
    "MEDIUM": {"bg": "#FFFBEB", "text": "#92400E", "dot": "#D97706", "border": "#FDE68A"},
    "NEEDS REVISION": {"bg": "#FFFBEB", "text": "#92400E", "dot": "#D97706", "border": "#FDE68A"},
    "NEEDS_REVISION": {"bg": "#FFFBEB", "text": "#92400E", "dot": "#D97706", "border": "#FDE68A"},
    "HIGH": {"bg": "#FEF2F2", "text": "#991B1B", "dot": "#DC2626", "border": "#FECACA"},
    "CRITICAL": {"bg": "#FEF2F2", "text": "#991B1B", "dot": "#DC2626", "border": "#FECACA"},
    "REJECTED": {"bg": "#FEF2F2", "text": "#991B1B", "dot": "#DC2626", "border": "#FECACA"},
    "INFEASIBLE": {"bg": "#FEF2F2", "text": "#991B1B", "dot": "#DC2626", "border": "#FECACA"},
    "FAILED": {"bg": "#FEF2F2", "text": "#991B1B", "dot": "#DC2626", "border": "#FECACA"},
    "PENDING": {"bg": "#F8FAFC", "text": "#475569", "dot": "#94A3B8", "border": "#E2E8F0"},
}


def get_status_style(status: Optional[str]) -> Dict[str, str]:
    """Return styling dictionary for a given status string."""
    if not status:
        return STATUS_CONFIG["PENDING"]
    normalized = str(status).strip().upper()
    return STATUS_CONFIG.get(normalized, STATUS_CONFIG["PENDING"])


def render_status_pill(status: Optional[str], custom_label: Optional[str] = None) -> str:
    """Return an inline HTML status pill with a colored CSS dot."""
    if not status:
        return '<span style="color: #64748B; font-size: 11px; font-weight: 500;">PENDING</span>'

    style = get_status_style(status)
    label = custom_label if custom_label else str(status).upper()

    return (
        f'<span style="display: inline-flex; align-items: center; background-color: {style["bg"]}; '
        f'color: {style["text"]}; border: 1px solid {style["border"]}; border-radius: 9999px; '
        f'padding: 2px 10px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; white-space: nowrap;">'
        f'<span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; '
        f'background-color: {style["dot"]}; margin-right: 6px;"></span>'
        f'{label}'
        f'</span>'
    )


def render_status_text(status: Optional[str]) -> str:
    """Return inline HTML for status pill without icons or emojis."""
    return render_status_pill(status)


def render_workflow_bar(pipeline_stages: Optional[List[Dict[str, Any]]], current_page_index: int) -> None:
    """Render a guided 5-step workflow stepper with numeric badges and status pills."""
    steps = [
        {"num": 1, "title": "Data and forecast", "key": "Data"},
        {"num": 2, "title": "Inventory and materials", "key": "Material risk"},
        {"num": 3, "title": "Agent analysis", "key": "Production impact"},
        {"num": 4, "title": "Procurement and production", "key": "Optimise"},
        {"num": 5, "title": "Governance and approval", "key": "Approval"},
    ]

    stage_status_map: Dict[str, str] = {}
    if pipeline_stages:
        for s in pipeline_stages:
            if isinstance(s, dict) and "stage" in s:
                stage_status_map[s["stage"]] = s.get("status", "PENDING")

    html_parts = [
        '<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
        'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04); '
        'padding: 12px 16px; margin-bottom: 24px;">'
        '<div style="display: flex; justify-content: space-between; align-items: center; '
        'flex-wrap: wrap; gap: 12px;">'
    ]

    for step in steps:
        idx = step["num"]
        title = step["title"]
        stage_key = step["key"]
        status = stage_status_map.get(stage_key, "PENDING")

        is_current = (idx == current_page_index)
        is_completed = str(status).upper() in ("COMPLETED", "VALIDATED", "APPROVED")

        # Visual indicator styling
        if is_current:
            badge_bg = "#0284C7"
            badge_color = "#FFFFFF"
            border_bottom = "border-bottom: 2px solid #0284C7;"
            title_weight = "700"
            title_color = "#0F172A"
        elif is_completed:
            badge_bg = "#10B981"
            badge_color = "#FFFFFF"
            border_bottom = "border-bottom: 2px solid transparent;"
            title_weight = "500"
            title_color = "#334155"
        else:
            badge_bg = "#F1F5F9"
            badge_color = "#64748B"
            border_bottom = "border-bottom: 2px solid transparent;"
            title_weight = "500"
            title_color = "#64748B"

        pill_html = render_status_pill(status)

        html_parts.append(
            f'<div style="display: flex; align-items: center; gap: 8px; {border_bottom} padding-bottom: 4px;">'
            f'<div style="width: 22px; height: 22px; border-radius: 50%; background-color: {badge_bg}; '
            f'color: {badge_color}; display: flex; align-items: center; justify-content: center; '
            f'font-size: 11px; font-weight: 700;">{idx}</div>'
            f'<div style="display: flex; flex-direction: column;">'
            f'<span style="font-size: 12px; font-weight: {title_weight}; color: {title_color};">{title}</span>'
            f'<div style="margin-top: 2px;">{pill_html}</div>'
            f'</div>'
            f'</div>'
        )

    html_parts.append("</div></div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_launchpad(on_run_callback=None) -> None:
    """Render an engaging executive zero-state launchpad."""
    st.markdown(
        """
        <div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px;
                    box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05); padding: 24px; margin-bottom: 24px;">
            <div style="border-left: 4px solid #0284C7; padding-left: 14px; margin-bottom: 16px;">
                <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.06em;">
                    System Status: Data Loaded and Ready for Orchestration
                </div>
                <h2 style="font-size: 18px; font-weight: 700; color: #0F172A; margin: 4px 0;">
                    Enterprise Pharmaceutical Supply Chain Resilience Launchpad
                </h2>
                <p style="font-size: 13px; color: #64748B; margin: 0; line-height: 1.5;">
                    Autonomous multi-agent intelligence platform synthesizing multi-echelon MRP, SKU demand forecasting,
                    and linear procurement optimization to protect essential drug availability.
                </p>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0;">
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-top: 3px solid #0284C7; border-radius: 6px; padding: 14px;">
                    <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; margin-bottom: 4px;">Pillar 1</div>
                    <div style="font-size: 13px; font-weight: 600; color: #0F172A; margin-bottom: 6px;">Demand Intelligence</div>
                    <div style="font-size: 12px; color: #64748B; line-height: 1.4;">
                        Statistical and ML horizon projections across 24-month regional sales records.
                    </div>
                </div>
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-top: 3px solid #0D9488; border-radius: 6px; padding: 14px;">
                    <div style="font-size: 11px; font-weight: 700; color: #0D9488; text-transform: uppercase; margin-bottom: 4px;">Pillar 2</div>
                    <div style="font-size: 13px; font-weight: 600; color: #0F172A; margin-bottom: 6px;">Inventory and MRP</div>
                    <div style="font-size: 12px; color: #64748B; line-height: 1.4;">
                        BOM explosion for 8 medicines against 19 materials, scrap factors, and warehouse lots.
                    </div>
                </div>
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-top: 3px solid #D97706; border-radius: 6px; padding: 14px;">
                    <div style="font-size: 11px; font-weight: 700; color: #D97706; text-transform: uppercase; margin-bottom: 4px;">Pillar 3</div>
                    <div style="font-size: 13px; font-weight: 600; color: #0F172A; margin-bottom: 6px;">Multi-Agent Swarm</div>
                    <div style="font-size: 12px; color: #64748B; line-height: 1.4;">
                        4 specialist agents evaluating lead-time volatility, line constraints, and GMP compliance.
                    </div>
                </div>
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-top: 3px solid #10B981; border-radius: 6px; padding: 14px;">
                    <div style="font-size: 11px; font-weight: 700; color: #10B981; text-transform: uppercase; margin-bottom: 4px;">Pillar 4</div>
                    <div style="font-size: 13px; font-weight: 600; color: #0F172A; margin-bottom: 6px;">Prescriptive Optimization</div>
                    <div style="font-size: 12px; color: #64748B; line-height: 1.4;">
                        Mixed-integer linear programming allocating purchase quantities under budget and MOQ constraints.
                    </div>
                </div>
            </div>
            <div style="background-color: #F1F5F9; border-radius: 6px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 12px; color: #334155;">
                    <b>Catalog readiness:</b> 8 finished drugs | 19 raw materials | 8 global suppliers | 24 active lots | 10 production orders
                </div>
                <div style="font-size: 11px; font-weight: 600; color: #10B981;">
                    ALL REPOSITORIES SYNCHRONIZED
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(message: str = "No results yet. Run analysis from Overview.") -> None:
    """Display an empty state message formatted inside an elevated card."""
    st.markdown(
        f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
        f'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04); '
        f'padding: 32px; text-align: center; margin: 16px 0;">'
        f'<div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">Analysis required</div>'
        f'<p style="color: #334155; font-size: 14px; font-weight: 500; margin: 0;">{message}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_synthetic_notice() -> None:
    """Display synthetic data disclaimer required by the contract."""
    st.markdown(
        '<div style="font-size: 11px; color: #64748B; margin-bottom: 12px; letter-spacing: 0.02em;">'
        'Dataset: Synthetic pharmaceutical supply chain model. All data and metrics are generated for decision-support simulation.'
        '</div>',
        unsafe_allow_html=True,
    )


def render_error_notice(error_message: str) -> None:
    """Display a clean error notice card with crimson accent."""
    st.markdown(
        f'<div style="background-color: #FFFFFF; border: 1px solid #FECACA; border-left: 4px solid #DC2626; '
        f'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04); padding: 14px 18px; margin: 12px 0;">'
        f'<div style="color: #991B1B; font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em;">Operational Notice</div>'
        f'<p style="color: #0F172A; font-size: 13px; margin: 4px 0 0 0;">{error_message}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
