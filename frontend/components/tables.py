"""Enterprise Table rendering components for MedChain AI.

Clean table presentation, sentence case column labels, CSV export capability.
Strict styling: Zero emojis, subtle borders, high-contrast typography.
"""

from __future__ import annotations

from typing import Optional
import pandas as pd
import streamlit as st


def render_table(
    df: Optional[pd.DataFrame],
    title: Optional[str] = None,
    empty_message: str = "No records to display.",
    download_filename: Optional[str] = None,
    use_container_width: bool = True,
) -> None:
    """Render a DataFrame with enterprise formatting and optional CSV export."""
    if title:
        st.markdown(
            f'<div style="font-size: 13px; font-weight: 700; color: #0F172A; text-transform: uppercase; '
            f'letter-spacing: 0.04em; margin: 16px 0 8px 0;">{title}</div>',
            unsafe_allow_html=True,
        )

    if df is None or df.empty:
        st.markdown(
            f'<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
            f'border-radius: 8px; box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04); '
            f'padding: 24px; text-align: center; color: #64748B; font-size: 13px;">'
            f'{empty_message}'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # Clean display
    st.dataframe(df, use_container_width=use_container_width, hide_index=True)

    if download_filename:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV report",
            data=csv_bytes,
            file_name=download_filename,
            mime="text/csv",
            key=f"dl_{download_filename}",
        )


def render_alerts_table(alerts_df: Optional[pd.DataFrame]) -> None:
    """Render priority alerts table."""
    if alerts_df is None or alerts_df.empty:
        st.markdown(
            '<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
            'border-radius: 8px; box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04); '
            'padding: 24px; text-align: center; color: #64748B; font-size: 13px;">'
            'No active priority alerts reported.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    render_table(
        alerts_df,
        title="Priority operational alerts",
        download_filename="priority_alerts.csv",
    )
