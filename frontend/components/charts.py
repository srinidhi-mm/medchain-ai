"""Enterprise Plotly chart components for MedChain AI.

Strict styling:
- ZERO emojis or decorative icons.
- Primary Pharma Blue (#0284C7) for actual historical data.
- Medical Teal / Emerald (#0D9488 / #10B981) for forecast predictions.
- Crimson (#DC2626) / Amber (#D97706) / Emerald (#10B981) reserved strictly for risk.
- High-contrast Inter / sans-serif typography, subtle gridlines (#F1F5F9).
"""

from __future__ import annotations

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PRIMARY_BLUE = "#0284C7"
FORECAST_TEAL = "#0D9488"
BORDER_GRAY = "#E2E8F0"
GRID_GRAY = "#F1F5F9"
TEXT_COLOR = "#0F172A"
MUTED_TEXT = "#64748B"
RISK_CRIMSON = "#DC2626"
RISK_AMBER = "#D97706"
RISK_EMERALD = "#10B981"


def _apply_minimal_layout(fig: go.Figure, title: str, x_title: str = "", y_title: str = "") -> None:
    """Apply consistent high-density enterprise styling to a Plotly figure."""
    fig.update_layout(
        title={
            "text": title,
            "font": {"size": 14, "color": TEXT_COLOR, "family": "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif"},
            "x": 0.0,
            "xanchor": "left",
        },
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font={"color": TEXT_COLOR, "family": "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif", "size": 12},
        margin={"l": 40, "r": 20, "t": 48, "b": 40},
        xaxis={
            "title": {"text": x_title, "font": {"size": 11, "color": MUTED_TEXT}},
            "showgrid": False,
            "linecolor": BORDER_GRAY,
            "tickfont": {"color": MUTED_TEXT, "size": 11},
        },
        yaxis={
            "title": {"text": y_title, "font": {"size": 11, "color": MUTED_TEXT}},
            "showgrid": True,
            "gridcolor": GRID_GRAY,
            "linecolor": BORDER_GRAY,
            "tickfont": {"color": MUTED_TEXT, "size": 11},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1.0,
            "font": {"size": 11, "color": MUTED_TEXT},
        },
    )


def render_demand_chart(
    historical_df: Optional[pd.DataFrame],
    forecast_df: Optional[pd.DataFrame],
    title: str = "Demand trajectory: historical vs predicted",
    medicine_name: Optional[str] = None,
) -> None:
    """Render the primary demand time series chart (blue = actual, teal = forecast)."""
    fig = go.Figure()

    chart_title = f"{title} ({medicine_name})" if medicine_name else title
    has_data = False

    # Historical sales trace (blue)
    if (
        historical_df is not None
        and not historical_df.empty
        and "date" in historical_df.columns
        and "units" in historical_df.columns
    ):
        hist_sorted = historical_df.sort_values("date")
        fig.add_trace(
            go.Scatter(
                x=hist_sorted["date"],
                y=hist_sorted["units"],
                mode="lines+markers",
                name="Historical actual demand",
                line={"color": PRIMARY_BLUE, "width": 2.5},
                marker={"size": 4, "color": PRIMARY_BLUE},
            )
        )
        has_data = True

    # Forecast trace (teal)
    if (
        forecast_df is not None
        and not forecast_df.empty
        and "date" in forecast_df.columns
        and "predicted" in forecast_df.columns
    ):
        fc_sorted = forecast_df.sort_values("date")

        # Confidence interval band (only if lower and upper exist and are populated)
        if "lower" in fc_sorted.columns and "upper" in fc_sorted.columns:
            valid_band = fc_sorted.dropna(subset=["lower", "upper"])
            if not valid_band.empty:
                fig.add_trace(
                    go.Scatter(
                        x=valid_band["date"].tolist() + valid_band["date"].tolist()[::-1],
                        y=valid_band["upper"].tolist() + valid_band["lower"].tolist()[::-1],
                        fill="toself",
                        fillcolor="rgba(13, 148, 136, 0.10)",
                        line={"color": "rgba(255,255,255,0)"},
                        hoverinfo="skip",
                        showlegend=True,
                        name="95% Confidence interval",
                    )
                )

        fig.add_trace(
            go.Scatter(
                x=fc_sorted["date"],
                y=fc_sorted["predicted"],
                mode="lines+markers",
                name="Projected demand",
                line={"color": FORECAST_TEAL, "width": 2.5, "dash": "solid"},
                marker={"size": 4, "color": FORECAST_TEAL},
            )
        )
        has_data = True

    if not has_data:
        st.markdown(
            '<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
            'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04); '
            'padding: 32px; text-align: center; color: #64748B; font-size: 13px;">'
            'No demand data points available for this selection.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    _apply_minimal_layout(fig, chart_title, x_title="Date", y_title="Units")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_demand_change_bar_chart(demand_growth_df: Optional[pd.DataFrame]) -> None:
    """Render demand change bar chart comparing medicines."""
    if demand_growth_df is None or demand_growth_df.empty:
        st.markdown(
            '<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
            'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04); '
            'padding: 24px; text-align: center; color: #64748B; font-size: 13px;">'
            'No demand growth figures available.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    df = demand_growth_df.copy()
    label_col = "medicine_name" if "medicine_name" in df.columns else "medicine_id"
    val_col = "growth_pct" if "growth_pct" in df.columns else "predicted_avg"

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df[label_col],
            y=df[val_col],
            marker_color=PRIMARY_BLUE,
            name="Projected change",
        )
    )

    _apply_minimal_layout(fig, "Projected demand variance by pharmaceutical product", x_title="Product", y_title="% Change")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_shortage_bar_chart(inventory_df: Optional[pd.DataFrame]) -> None:
    """Render shortage bar chart by material."""
    if inventory_df is None or inventory_df.empty:
        st.markdown(
            '<div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; '
            'border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04); '
            'padding: 24px; text-align: center; color: #64748B; font-size: 13px;">'
            'No raw material inventory balance data available.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    df = inventory_df.copy()
    mat_col = "material" if "material" in df.columns else "material_id"
    short_col = "shortage" if "shortage" in df.columns else "required"

    colors = []
    for _, row in df.iterrows():
        risk = str(row.get("risk", "")).lower()
        if "crit" in risk or "high" in risk:
            colors.append(RISK_CRIMSON)
        elif "med" in risk:
            colors.append(RISK_AMBER)
        else:
            colors.append(RISK_EMERALD)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df[mat_col],
            y=df[short_col],
            marker_color=colors,
            name="Shortage units",
        )
    )

    _apply_minimal_layout(fig, "Projected raw material shortage exposure", x_title="Material code / description", y_title="Shortage Quantity")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_simulation_comparison_chart(comparison_df: Optional[pd.DataFrame]) -> None:
    """Render grouped bar chart comparing baseline vs scenario values."""
    if comparison_df is None or comparison_df.empty:
        return

    df = comparison_df.copy()
    fig = go.Figure()

    if "baseline" in df.columns:
        fig.add_trace(
            go.Bar(
                x=df["measure"],
                y=df["baseline"],
                name="Baseline operational model",
                marker_color=PRIMARY_BLUE,
            )
        )
    if "scenario" in df.columns:
        fig.add_trace(
            go.Bar(
                x=df["measure"],
                y=df["scenario"],
                name="Disrupted scenario outcome",
                marker_color=RISK_AMBER,
            )
        )

    _apply_minimal_layout(fig, "Disruption stress-test: baseline vs scenario impact", x_title="Operational Metric", y_title="Quantity / Level")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
