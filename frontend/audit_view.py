"""Decision and Audit History view for MedChain AI.

Features:
- Immutable audit trail table with standardized columns (decision_id, time, source, summary, medicine, material, validation, approval, type, references).
- Search input across all textual fields.
- Multi-dimensional filters (source agent, validation status, approval status).
- CSV export for regulatory documentation and compliance review.
- Detailed inspect-one-record inspector card.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd
import streamlit as st
from frontend.components.status_components import render_empty_state, render_status_pill
from frontend.components.tables import render_table
from frontend.data_access import get_audit_records


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the Decision and audit history view."""
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                Compliance Governance
            </div>
            <h1 style="font-size: 20px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                21 CFR Part 11 Electronic Decision and Audit Trail
            </h1>
            <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                Immutable traceability of autonomous agent reasoning, risk thresholds, and human-in-the-loop authorizations
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Fetch audit records from backend adapter
    audit_df, err = get_audit_records()

    if audit_df is None or audit_df.empty:
        render_empty_state("No audit records found in the database. Decisions logged during pipeline execution will appear here.")
        return

    df = audit_df.copy()

    # 1. Search and Filtering Controls
    s_col1, f_col1, f_col2, f_col3 = st.columns([4, 2, 2, 2])

    with s_col1:
        search_kw = st.text_input("Search audit records", key="audit_search_input", placeholder="Filter by ID, description, or medicine...")

    # Filter by source agent
    source_options = ["All sources"]
    if "source" in df.columns:
        source_options.extend(df["source"].dropna().unique().tolist())
    with f_col1:
        selected_source = st.selectbox("Source agent", options=source_options, key="audit_filter_source")

    # Filter by validation status
    val_options = ["All statuses"]
    if "validation" in df.columns:
        val_options.extend(df["validation"].dropna().unique().tolist())
    with f_col2:
        selected_val = st.selectbox("Validation", options=val_options, key="audit_filter_val")

    # Filter by approval status
    app_options = ["All approvals"]
    if "approval" in df.columns:
        app_options.extend(df["approval"].dropna().unique().tolist())
    with f_col3:
        selected_app = st.selectbox("Approval", options=app_options, key="audit_filter_app")

    # Apply filters
    filtered_df = df.copy()

    if search_kw:
        q = search_kw.lower()
        mask = filtered_df.astype(str).apply(lambda row: row.str.lower().str.contains(q, na=False).any(), axis=1)
        filtered_df = filtered_df[mask]

    if selected_source != "All sources" and "source" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["source"] == selected_source]

    if selected_val != "All statuses" and "validation" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["validation"] == selected_val]

    if selected_app != "All approvals" and "approval" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["approval"] == selected_app]

    # 2. Main Audit Trail Table
    render_table(
        filtered_df,
        title="21 CFR Part 11 Compliant Audit Log",
        empty_message="No audit trail entries match your search criteria.",
        download_filename="audit_trail_export.csv",
    )

    st.markdown('<div style="margin-top: 28px; border-top: 1px solid #E2E8F0; padding-top: 18px;"></div>', unsafe_allow_html=True)

    # 3. Inspect-One-Record View
    st.markdown(
        '<div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
        'letter-spacing: 0.04em; margin-bottom: 8px;">Detailed Record Inspector</div>',
        unsafe_allow_html=True,
    )

    record_ids = []
    if "decision_id" in filtered_df.columns:
        record_ids = filtered_df["decision_id"].dropna().tolist()
    elif not filtered_df.empty:
        record_ids = [str(i) for i in filtered_df.index]

    if record_ids:
        insp_col, _ = st.columns([4, 6])
        with insp_col:
            selected_rec_id = st.selectbox("Select record ID to inspect", options=record_ids, key="audit_inspect_select")

        # Find record
        matched = pd.DataFrame()
        if "decision_id" in filtered_df.columns:
            matched = filtered_df[filtered_df["decision_id"] == selected_rec_id]
        else:
            matched = filtered_df.loc[[int(selected_rec_id)]]

        if not matched.empty:
            rec = matched.iloc[0].to_dict()

            val_status = rec.get("validation", "PENDING")
            app_status = rec.get("approval", "PENDING")

            val_pill = render_status_pill(str(val_status))
            app_pill = render_status_pill(str(app_status))

            card_html = (
                f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-top: 3px solid #0284C7; '
                f'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05); padding: 20px; margin-top: 10px;">'
                f'<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">'
                f'<div>'
                f'<div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase;">Audit Identification</div>'
                f'<div style="font-size: 16px; font-weight: 800; color: #0F172A;">{rec.get("decision_id", selected_rec_id)}</div>'
                f'</div>'
                f'<div style="display: flex; gap: 8px;">'
                f'{val_pill} {app_pill}'
                f'</div>'
                f'</div>'
                f'<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; background-color: #F8FAFC; '
                f'border-radius: 6px; padding: 12px; margin-bottom: 14px; font-size: 12px;">'
                f'<div><span style="color: #64748B;">Timestamp:</span> <b style="color: #0F172A;">{rec.get("time", "N/A")}</b></div>'
                f'<div><span style="color: #64748B;">Source:</span> <b style="color: #0F172A;">{rec.get("source", "N/A")}</b></div>'
                f'<div><span style="color: #64748B;">Action Type:</span> <b style="color: #0F172A;">{rec.get("type", "N/A")}</b></div>'
                f'<div><span style="color: #64748B;">Medicine:</span> <b style="color: #0F172A;">{rec.get("medicine", "N/A")}</b></div>'
                f'<div><span style="color: #64748B;">Material:</span> <b style="color: #0F172A;">{rec.get("material", "N/A")}</b></div>'
                f'<div><span style="color: #64748B;">References:</span> <b style="color: #0F172A;">{rec.get("references", "N/A")}</b></div>'
                f'</div>'
                f'<div style="font-size: 13px; color: #1E293B; line-height: 1.5;">'
                f'<b>Decision Rationale:</b> {rec.get("summary", "No summary recorded.")}'
                f'</div>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
