"""Enterprise KPI Card components for MedChain AI.

Strict styling:
- Zero emojis or icons.
- Top accent border (3px solid) indicating category or severity.
- Contextual status pills with colored CSS dots.
- Elevated surface: subtle border, 8px radius, refined box-shadow.
- High-contrast typography: deep navy values (#0F172A), muted slate labels (#64748B).
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st
from frontend.components.status_components import render_status_pill


def render_kpi_card(
    label: str,
    value: Any,
    subtext: Optional[str] = None,
    status: Optional[str] = None,
    accent_color: str = "#0284C7",
) -> None:
    """Render a polished enterprise KPI card with top accent border and status pill."""
    display_value = str(value) if value is not None else "Not available"

    pill_html = render_status_pill(status) if status else ""
    subtext_html = (
        f'<div style="font-size: 12px; color: #64748B; margin-top: 6px; font-weight: 500;">{subtext}</div>'
        if subtext
        else ""
    )

    card_html = (
        f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-top: 3px solid {accent_color}; '
        f'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05); '
        f'padding: 14px 16px; margin-bottom: 12px; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">'
        f'<div>'
        f'<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; gap: 6px;">'
        f'<span style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em;">{label}</span>'
        f'{pill_html}'
        f'</div>'
        f'<div style="font-size: 26px; font-weight: 700; color: #0F172A; line-height: 1.1; letter-spacing: -0.02em;">{display_value}</div>'
        f'</div>'
        f'{subtext_html}'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def render_overview_kpis(kpis: Optional[Dict[str, Any]]) -> None:
    """Render the six primary overview KPI cards in a 6-column enterprise grid."""
    kpi_dict = kpis or {}
    cols = st.columns(6)

    # 1. Medicines
    med_count = kpi_dict.get("medicines")
    with cols[0]:
        render_kpi_card(
            label="Finished medicines",
            value=med_count,
            subtext="Catalog portfolio",
            status="READY",
            accent_color="#0284C7",
        )

    # 2. Raw Materials
    mat_count = kpi_dict.get("materials")
    with cols[1]:
        render_kpi_card(
            label="Active materials",
            value=mat_count,
            subtext="APIs, excipients, packaging",
            status="READY",
            accent_color="#0D9488",
        )

    # 3. Critical Shortages
    short_count = kpi_dict.get("critical_shortages") or 0
    short_status = "CRITICAL" if short_count > 0 else "LOW"
    short_accent = "#DC2626" if short_count > 0 else "#10B981"
    with cols[2]:
        render_kpi_card(
            label="Stockout exposure",
            value=short_count,
            subtext="Materials below safety buffer",
            status=short_status,
            accent_color=short_accent,
        )

    # 4. High-Risk Suppliers
    sup_risk = kpi_dict.get("high_risk_suppliers") or 0
    sup_status = "HIGH" if sup_risk > 0 else "LOW"
    sup_accent = "#DC2626" if sup_risk > 0 else "#10B981"
    with cols[3]:
        render_kpi_card(
            label="High-risk vendors",
            value=sup_risk,
            subtext="Lead time / quality flags",
            status=sup_status,
            accent_color=sup_accent,
        )

    # 5. Orders at Risk
    orders_risk = kpi_dict.get("orders_at_risk") or 0
    ord_status = "MEDIUM" if orders_risk > 0 else "LOW"
    ord_accent = "#D97706" if orders_risk > 0 else "#10B981"
    with cols[4]:
        render_kpi_card(
            label="Batches impacted",
            value=orders_risk,
            subtext="Production schedule alerts",
            status=ord_status,
            accent_color=ord_accent,
        )

    # 6. Pending Approvals
    pending_app = kpi_dict.get("pending_approvals") or 0
    app_status = "NEEDS REVISION" if pending_app > 0 else "COMPLETED"
    app_accent = "#D97706" if pending_app > 0 else "#10B981"
    with cols[5]:
        render_kpi_card(
            label="Pending sign-offs",
            value=pending_app,
            subtext="21 CFR Part 11 queue",
            status=app_status,
            accent_color=app_accent,
        )


def render_procurement_kpis(proc_kpis: Optional[Dict[str, Any]]) -> None:
    """Render the three procurement KPI cards."""
    pk = proc_kpis or {}
    cols = st.columns(3)

    cost_val = pk.get("estimated_cost")
    cost_str = f"${cost_val:,.2f}" if isinstance(cost_val, (int, float)) else cost_val
    req_count = pk.get("requirements")
    crit_count = pk.get("critical") or 0
    crit_status = "CRITICAL" if crit_count > 0 else "OPTIMAL"
    crit_accent = "#DC2626" if crit_count > 0 else "#10B981"

    with cols[0]:
        render_kpi_card(
            label="Procurement orders required",
            value=req_count,
            subtext="Identified by MRP engine",
            status="READY",
            accent_color="#0284C7",
        )
    with cols[1]:
        render_kpi_card(
            label="Total purchase exposure",
            value=cost_str,
            subtext="Pre-optimization baseline",
            status="READY",
            accent_color="#0D9488",
        )
    with cols[2]:
        render_kpi_card(
            label="Urgent procurement batches",
            value=crit_count,
            subtext="Immediate PO release required",
            status=crit_status,
            accent_color=crit_accent,
        )
