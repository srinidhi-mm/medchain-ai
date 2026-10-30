"""Backend Data Access Adapter for MedChain AI.

This module acts as the single boundary between the backend systems and the UI.
It resolves backend calls dynamically, catches all exceptions, reshapes raw
payloads to match the strict frontend contract, and never raises exceptions.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

# Canonical backend function mapping
BACKEND: Dict[str, Tuple[str, str]] = {
    "run_pipeline": ("orchestration.graph", "run_pipeline"),
    "forecast": ("forecasting.demand_forecaster", "generate_forecast"),
    "evaluation": ("forecasting.evaluation", "evaluate_forecasts"),
    "inventory": ("planning.inventory_planner", "calculate_inventory_status"),
    "bom": ("planning.bom_calculator", "get_bom_breakdown"),
    "procurement": ("procurement.procurement_planner", "generate_purchase_recommendations"),
    "optimise": ("optimization.procurement_optimizer", "optimize_procurement"),
    "simulate": ("simulation.disruption_engine", "run_simulation"),
    "approve": ("services.approval_service", "record_approval_decision"),
    "audit": ("database.audit_logger", "get_audit_records"),
    "status": ("core.coordinator", "get_system_status"),
}


def call(key: str, **kwargs: Any) -> Tuple[Optional[Any], Optional[str]]:
    """Execute a backend function safely. Never raises an exception."""
    if key not in BACKEND:
        return None, f"Unknown backend key: {key}"

    module_name, func_name = BACKEND[key]
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        result = func(**kwargs)
        return result, None
    except ImportError as e:
        return None, f"Module '{module_name}' could not be imported: {e}"
    except AttributeError:
        return None, f"Function '{func_name}' not found in module '{module_name}'"
    except Exception as e:
        return None, f"Backend execution error in '{key}': {str(e)}"


def get_empty_results() -> Dict[str, Any]:
    """Construct an empty results payload matching the frontend schema."""
    return {
        "pipeline": [],
        "kpis": {},
        "medicines": pd.DataFrame(columns=["medicine_id", "medicine_name"]),
        "sales": pd.DataFrame(columns=["date", "medicine_id", "units"]),
        "forecast": pd.DataFrame(columns=["date", "medicine_id", "predicted", "lower", "upper"]),
        "demand_growth": pd.DataFrame(
            columns=["medicine_id", "medicine_name", "current_avg", "predicted_avg", "growth_pct", "status"]
        ),
        "evaluation": pd.DataFrame(columns=["medicine_id", "mae", "rmse", "mape"]),
        "explanations": {},
        "alerts": pd.DataFrame(columns=["alert_id", "severity", "title", "description", "timestamp"]),
        "log": pd.DataFrame(columns=["timestamp", "agent", "action", "status", "details"]),
        "schedule": pd.DataFrame(
            columns=["order_id", "medicine_id", "medicine_name", "line_id", "start_date", "due_date", "status"]
        ),
        "suppliers": pd.DataFrame(
            columns=["supplier_id", "name", "country", "reliability", "quality", "lead_time", "gmp"]
        ),
        "inventory": pd.DataFrame(
            columns=["material_id", "material", "available", "reserved", "incoming", "required", "shortage", "risk"]
        ),
        "bom": pd.DataFrame(
            columns=["medicine_id", "material", "per_unit", "required", "available", "shortage"]
        ),
        "lots": pd.DataFrame(columns=["material", "lot", "quantity", "expiry"]),
        "agents": [],
        "guard": {
            "status": None,
            "revision": 0,
            "max_revision": 3,
            "checks": pd.DataFrame(columns=["check_name", "category", "status", "details"]),
        },
        "decisions": [],
        "proc_kpis": {},
        "procurement": pd.DataFrame(
            columns=[
                "rec_id",
                "material",
                "required",
                "available",
                "suggested_qty",
                "supplier",
                "cost",
                "delivery",
                "status",
            ]
        ),
        "sim_options": {
            "Demand spike": [],
            "Supplier delay": [],
            "Material shortage": [],
            "Capacity reduction": [],
        },
    }


def reshape_pipeline_output(raw: Any) -> Dict[str, Any]:
    """Reshape arbitrary backend output to fit the UI contract."""
    base = get_empty_results()
    if not isinstance(raw, dict):
        return base

    # Pipeline stages
    if "pipeline" in raw and isinstance(raw["pipeline"], list):
        base["pipeline"] = [
            {"stage": s.get("stage", "Unknown"), "status": s.get("status", "Pending")}
            for s in raw["pipeline"]
            if isinstance(s, dict)
        ]

    # Overview KPIs
    if "kpis" in raw and isinstance(raw["kpis"], dict):
        base["kpis"] = {
            "medicines": raw["kpis"].get("medicines"),
            "materials": raw["kpis"].get("materials"),
            "critical_shortages": raw["kpis"].get("critical_shortages"),
            "high_risk_suppliers": raw["kpis"].get("high_risk_suppliers"),
            "orders_at_risk": raw["kpis"].get("orders_at_risk"),
            "pending_approvals": raw["kpis"].get("pending_approvals"),
        }

    # DataFrames
    for df_key in [
        "medicines",
        "sales",
        "forecast",
        "demand_growth",
        "evaluation",
        "alerts",
        "log",
        "schedule",
        "suppliers",
        "inventory",
        "bom",
        "lots",
        "procurement",
    ]:
        if df_key in raw:
            val = raw[df_key]
            if isinstance(val, pd.DataFrame):
                base[df_key] = val
            elif isinstance(val, list):
                base[df_key] = pd.DataFrame(val)

    # Explanations
    if "explanations" in raw and isinstance(raw["explanations"], dict):
        base["explanations"] = raw["explanations"]

    # Agents list
    if "agents" in raw and isinstance(raw["agents"], list):
        base["agents"] = raw["agents"]

    # Quality Guard
    if "guard" in raw and isinstance(raw["guard"], dict):
        base["guard"] = {
            "status": raw["guard"].get("status"),
            "revision": raw["guard"].get("revision", 0),
            "max_revision": raw["guard"].get("max_revision", 3),
            "checks": raw["guard"].get("checks", pd.DataFrame()),
        }
        if not isinstance(base["guard"]["checks"], pd.DataFrame):
            base["guard"]["checks"] = pd.DataFrame(base["guard"]["checks"])

    # Decisions
    if "decisions" in raw and isinstance(raw["decisions"], list):
        base["decisions"] = raw["decisions"]

    # Procurement KPIs
    if "proc_kpis" in raw and isinstance(raw["proc_kpis"], dict):
        base["proc_kpis"] = raw["proc_kpis"]

    # Simulation options
    if "sim_options" in raw and isinstance(raw["sim_options"], dict):
        base["sim_options"] = raw["sim_options"]

    return base


def run_pipeline() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Trigger the pipeline runner, reshape, and store in session state."""
    raw_output, err = call("run_pipeline")
    if err:
        return None, err

    reshaped = reshape_pipeline_output(raw_output)
    st.session_state["results"] = reshaped
    return reshaped, None


def get_results() -> Optional[Dict[str, Any]]:
    """Retrieve existing analysis results from session state."""
    return st.session_state.get("results", None)


def get_system_status() -> Dict[str, str]:
    """Retrieve the current health and connectivity status of the system."""
    data, err = call("status")
    if err or not isinstance(data, dict):
        return {
            "data_status": "Synthetic dataset",
            "llm_status": "Unavailable",
            "database_status": "Connected (SQLite)",
            "version": "1.0.0",
        }
    return {
        "data_status": str(data.get("data_status", "Synthetic dataset")),
        "llm_status": str(data.get("llm_status", "Unavailable")),
        "database_status": str(data.get("database_status", "Connected")),
        "version": str(data.get("version", "1.0.0")),
    }


def run_forecast_regeneration(medicine_id: str, horizon_days: int) -> Tuple[Optional[Any], Optional[str]]:
    """Regenerate a forecast for a specific medicine and horizon."""
    return call("forecast", medicine_id=medicine_id, horizon_days=horizon_days)


def run_optimisation(budget: float, max_lead_time: int, apply_moq: bool) -> Tuple[Optional[Any], Optional[str]]:
    """Run procurement optimization."""
    return call("optimise", budget=budget, max_lead_time=max_lead_time, apply_moq=apply_moq)


def run_simulation(scenario: str, target: str, severity: float) -> Tuple[Optional[Any], Optional[str]]:
    """Run disruption simulation."""
    return call("simulate", scenario=scenario, target=target, severity=severity)


def record_approval(recommendation_id: str, decision: str, comment: str) -> Tuple[Optional[Any], Optional[str]]:
    """Record a human-in-the-loop approval decision."""
    return call("approve", recommendation_id=recommendation_id, decision=decision, comment=comment)


def get_audit_records() -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Fetch audit history."""
    data, err = call("audit")
    if err:
        return None, err
    if isinstance(data, pd.DataFrame):
        return data, None
    if isinstance(data, list):
        return pd.DataFrame(data), None
    return pd.DataFrame(columns=["decision_id", "time", "source", "summary", "medicine", "material", "validation", "approval", "type", "references"]), None

