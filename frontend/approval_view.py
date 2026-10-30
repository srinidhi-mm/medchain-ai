"""Approval workflow view for MedChain AI.

Workflow Step 5:
- Guided 5-step workflow stepper.
- Quality Guard regulatory gatekeeping status.
- Locked unless status is VALIDATED; REJECTED flags for manual review and locks all actions.
- 21 CFR Part 11 compliant decision recording form (mandatory comment on rejection).
- Historical approval decisions log table with CSV download.
- Policy safeguard notice: Never executes real purchases or contacts suppliers.
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
from frontend.data_access import get_audit_records, record_approval


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the human-in-the-loop Governance and approval workflow page."""
    # 1. Top Guided Stepper
    pipeline_state = results.get("pipeline") if results else None
    render_workflow_bar(pipeline_stages=pipeline_state, current_page_index=5)

    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                Workflow Step 5 of 5
            </div>
            <h1 style="font-size: 20px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                Governance, Regulatory Sign-off, and Approval
            </h1>
            <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                Human-in-the-loop oversight enforcing cGMP quality gatekeeping and 21 CFR Part 11 electronic audit logs
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Empty state check
    if not results or not any(results.get("kpis", {}).values()):
        render_empty_state("No results yet. Run analysis from Overview.")
        return

    # 2. Quality Guard Status & Gatekeeping
    guard_info = results.get("guard", {})
    guard_status = str(guard_info.get("status", "PENDING")).upper()
    rev_count = guard_info.get("revision", 0)
    max_rev = guard_info.get("max_revision", 3)

    status_pill = render_status_pill(guard_status)

    st.markdown(
        f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px;
                    box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05); padding: 16px 20px; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 13px; font-weight: 700; color: #0F172A;">Quality Guard Regulatory Gate</span>
                    {status_pill}
                </div>
                <div style="font-size: 12px; color: #475569;">
                    Revision cycles completed: <b>{rev_count} / {max_rev}</b>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    is_validated = guard_status == "VALIDATED"
    is_rejected = guard_status == "REJECTED"

    if is_rejected:
        st.markdown(
            """
            <div style="background-color: #FEF2F2; border: 1px solid #FECACA; border-left: 4px solid #DC2626;
                        border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <div style="color: #991B1B; font-weight: 700; font-size: 13px; text-transform: uppercase;">
                    Flagged for Formal Quality Review
                </div>
                <div style="color: #0F172A; font-size: 13px; margin-top: 4px; line-height: 1.4;">
                    Quality Guard detected critical compliance or supplier validation failures.
                    Autonomous purchase authorizations are locked. Manual Quality Assurance inspection is mandatory.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif not is_validated:
        st.markdown(
            """
            <div style="background-color: #FFFBEB; border: 1px solid #FDE68A; border-left: 4px solid #D97706;
                        border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <div style="color: #92400E; font-weight: 700; font-size: 13px; text-transform: uppercase;">
                    Approval Locked: Validation Pending
                </div>
                <div style="color: #0F172A; font-size: 13px; margin-top: 4px; line-height: 1.4;">
                    Approval actions are restricted until Quality Guard verification status reaches <b>VALIDATED</b>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3. Decision Recording Form
    st.markdown(
        '<div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
        'letter-spacing: 0.04em; margin: 16px 0 8px 0;">Record Sign-off Authorization</div>',
        unsafe_allow_html=True,
    )

    proc_df = results.get("procurement", pd.DataFrame())
    rec_options = []
    if isinstance(proc_df, pd.DataFrame) and not proc_df.empty:
        id_col = "rec_id" if "rec_id" in proc_df.columns else proc_df.columns[0]
        mat_col = "material" if "material" in proc_df.columns else id_col
        for _, row in proc_df.iterrows():
            r_id = str(row[id_col])
            r_mat = str(row[mat_col])
            rec_options.append(f"{r_id}: {r_mat}")

    with st.form("approval_decision_form"):
        selected_rec = st.selectbox(
            "Select purchase recommendation to evaluate",
            options=rec_options if rec_options else ["No recommendations pending approval"],
            disabled=not is_validated,
            key="approval_rec_select",
        )

        decision_choice = st.radio(
            "Authorization action",
            options=["Approve", "Reject"],
            horizontal=True,
            disabled=not is_validated,
            key="approval_decision_radio",
        )

        comment_text = st.text_area(
            "Reviewer justification remarks (Mandatory if rejecting)",
            placeholder="Document compliance verification rationale, quality notes, or audit trail remarks...",
            disabled=not is_validated,
            key="approval_comment_input",
        )

        submit_btn = st.form_submit_button(
            "Record signed decision",
            type="primary",
            disabled=not is_validated,
        )

    if submit_btn:
        rec_id = selected_rec.split(":")[0].strip() if ":" in selected_rec else selected_rec

        if decision_choice == "Reject" and not comment_text.strip():
            render_error_notice("Rejection requires mandatory documented justification in compliance remarks.")
        else:
            with st.spinner("Persisting authorized decision into 21 CFR Part 11 audit log..."):
                _, err = record_approval(
                    recommendation_id=rec_id,
                    decision=decision_choice,
                    comment=comment_text.strip(),
                )
                if err:
                    render_error_notice(f"Failed to record approval: {err}")
                else:
                    st.success(f"Audit record recorded: Recommendation {rec_id} marked as {decision_choice}.")
                    st.rerun()

    # Safety disclaimer
    st.markdown(
        '<div style="font-size: 11px; color: #64748B; margin-top: 10px;">'
        'Policy governance: Platform operates strictly in an advisory decision-support mode. Authorizations are recorded in '
        'immutable audit trails; the system will never directly execute bank transactions or contact vendors.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)

    # 4. Approval Decision History Log
    audit_df, _ = get_audit_records()
    approval_audit = pd.DataFrame()
    if isinstance(audit_df, pd.DataFrame) and not audit_df.empty:
        if "approval" in audit_df.columns:
            approval_audit = audit_df.dropna(subset=["approval"])
        else:
            approval_audit = audit_df

    render_table(
        approval_audit,
        title="21 CFR Part 11 Electronic signature and approval audit log",
        empty_message="No approval transactions recorded in the current session.",
        download_filename="approval_audit_trail.csv",
    )
