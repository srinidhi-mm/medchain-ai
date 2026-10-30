"""Inventory and Materials view for MedChain AI.

Workflow Step 2:
- Guided 5-step workflow stepper.
- Material inventory table with search, risk filter, and CSV download.
- Projected material shortage bar chart.
- Bill of Materials (BOM) breakdown filterable by medicine.
- Warehouse lot inventory & expiry details expander.
- 'Next step' button routing to Agent analysis.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd
import streamlit as st
from frontend.components.charts import render_shortage_bar_chart
from frontend.components.status_components import render_empty_state, render_workflow_bar
from frontend.components.tables import render_table


def render(results: Optional[Dict[str, Any]]) -> None:
    """Render the Inventory and materials workflow page."""
    # 1. Top Guided Stepper
    pipeline_state = results.get("pipeline") if results else None
    render_workflow_bar(pipeline_stages=pipeline_state, current_page_index=2)

    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #0284C7; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">
                Workflow Step 2 of 5
            </div>
            <h1 style="font-size: 20px; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em;">
                Inventory Balances and Material Requirements
            </h1>
            <div style="color: #64748B; font-size: 13px; margin-top: 4px;">
                Safety stock calculations, reorder point thresholds, and multi-level BOM explosion
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Empty state check
    if not results or not any(results.get("kpis", {}).values()):
        render_empty_state("No results yet. Run analysis from Overview.")
        st.button("Next step: Agent analysis", disabled=True, key="next_step_disabled_inventory")
        return

    inventory_df = results.get("inventory", pd.DataFrame())

    # 2. Material Shortage Bar Chart
    render_shortage_bar_chart(inventory_df)

    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # 3. Material Table Controls: Search & Risk Filter
    search_col, filter_col, _ = st.columns([4, 3, 3])
    with search_col:
        search_query = st.text_input("Search raw material", key="inv_search_input", placeholder="Filter by material name or code...")
    with filter_col:
        risk_filter = st.selectbox(
            "Filter by stockout risk",
            options=["All", "Critical", "High", "Medium", "Low"],
            key="inv_risk_select",
        )

    # Apply filters to inventory table
    filtered_inv = inventory_df.copy() if isinstance(inventory_df, pd.DataFrame) else pd.DataFrame()
    if not filtered_inv.empty:
        if search_query:
            q = search_query.lower()
            mask = filtered_inv.apply(
                lambda row: q in str(row.get("material", "")).lower() or q in str(row.get("material_id", "")).lower(),
                axis=1,
            )
            filtered_inv = filtered_inv[mask]

        if risk_filter != "All" and "risk" in filtered_inv.columns:
            filtered_inv = filtered_inv[filtered_inv["risk"].astype(str).str.lower() == risk_filter.lower()]

    # Render Material Table
    render_table(
        filtered_inv,
        title="Material stock, allocation, and net shortage matrix",
        empty_message="No materials match the filter criteria.",
        download_filename="material_inventory_status.csv",
    )

    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # 4. Bill of Materials (BOM) Breakdown by Medicine
    bom_df = results.get("bom", pd.DataFrame())
    medicines_df = results.get("medicines", pd.DataFrame())

    st.markdown(
        '<div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
        'letter-spacing: 0.04em; margin: 16px 0 8px 0;">Bill of Materials Explosion</div>',
        unsafe_allow_html=True,
    )

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

    col_bom_select, _ = st.columns([4, 6])
    with col_bom_select:
        selected_bom_med = st.selectbox(
            "Select medicine for BOM analysis",
            options=med_options if med_options else ["No medicines available"],
            key="bom_med_select",
        )

    selected_bom_id = med_id_map.get(selected_bom_med, "")
    filtered_bom = pd.DataFrame()
    if isinstance(bom_df, pd.DataFrame) and not bom_df.empty and "medicine_id" in bom_df.columns:
        filtered_bom = bom_df[bom_df["medicine_id"] == selected_bom_id]

    render_table(
        filtered_bom,
        empty_message="No BOM records reported for this medicine.",
        download_filename=f"bom_{selected_bom_id}.csv",
    )

    # 5. Expander for Lot and Expiry Details
    lots_df = results.get("lots", pd.DataFrame())
    if isinstance(lots_df, pd.DataFrame) and not lots_df.empty:
        with st.expander("Warehouse lot inventory and expiry details", expanded=False):
            render_table(
                lots_df,
                empty_message="No warehouse lot records available.",
                download_filename="warehouse_lot_inventory.csv",
            )

    # Footer Navigation: Next Step button
    st.markdown('<div style="margin-top: 36px; border-top: 1px solid #E2E8F0; padding-top: 18px;"></div>', unsafe_allow_html=True)
    col_dummy, col_next = st.columns([7, 3])
    with col_next:
        if st.button("Next step: Agent analysis", type="primary", use_container_width=True, key="btn_next_step_inventory"):
            st.session_state["page"] = "3. Agent analysis"
            st.rerun()
