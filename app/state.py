"""Session-state lifecycle for explicit operator calculations."""
from __future__ import annotations

import copy
from typing import Any, Callable

import streamlit as st

from app.kernel_bridge import default_plan_raw, input_hash, new_workspace, plan_hash, scenario_hash, stress_reference_raw


ANALYSIS_KEYS = (
    "risk_result",
    "risk_detail",
    "mitigation_result",
    "sensitivity_result",
    "reverse_result",
    "builder_result",
    "abc_result",
    "alternative_result",
    "export_files",
    "bundle",
)


def initialize(evaluator: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    if "plan" not in st.session_state:
        st.session_state.plan = default_plan_raw()
    if "result" not in st.session_state:
        st.session_state.result = evaluator(st.session_state.plan)
    st.session_state.setdefault("calculated_plan", copy.deepcopy(st.session_state.plan))
    st.session_state.setdefault("stress_plan", stress_reference_raw())
    st.session_state.setdefault("workspace", new_workspace())
    st.session_state.setdefault("research_plan", None)
    st.session_state.setdefault("research_result", None)
    st.session_state.setdefault("snapshots", {})
    st.session_state.setdefault("validation_result", None)
    st.session_state.setdefault("source_overrides", {})
    st.session_state.setdefault("custom_scenario", None)
    for key in ANALYSIS_KEYS:
        st.session_state.setdefault(key, None)


def is_dirty() -> bool:
    result = st.session_state.result
    if plan_hash(st.session_state.plan) != result.get("plan_hash"):
        return True
    if input_hash(st.session_state.get("source_overrides", {})) != result.get("input_hash", input_hash({})):
        return True
    custom = st.session_state.get("custom_scenario")
    calculated_custom = result.get("custom_scenario")
    if bool(custom) != bool(calculated_custom):
        return True
    if custom and calculated_custom:
        return scenario_hash(custom) != calculated_custom.get("scenario_hash")
    return False


def analysis_is_stale(value: dict[str, Any] | None) -> bool:
    if not value:
        return False
    return (
        value.get("plan_hash") != plan_hash(st.session_state.plan)
        or value.get("input_hash", input_hash({}))
        != input_hash(st.session_state.get("source_overrides", {}))
    )


def apply_plan(raw: dict[str, Any]) -> None:
    st.session_state.plan = copy.deepcopy(raw)
    st.session_state.validation_result = None


def accept_calculation(result: dict[str, Any]) -> None:
    st.session_state.result = result
    st.session_state.calculated_plan = copy.deepcopy(st.session_state.plan)
    for key in ANALYSIS_KEYS:
        st.session_state[key] = None


def save_snapshot() -> str:
    plan = copy.deepcopy(st.session_state.plan)
    key = f"{plan.get('plan_id', 'plan')} · {plan_hash(plan)}"
    st.session_state.snapshots[key] = plan
    return key


def reset_research(plan: dict[str, Any] | None = None) -> None:
    st.session_state.workspace = new_workspace()
    st.session_state.research_plan = copy.deepcopy(plan or st.session_state.plan)
    st.session_state.research_result = None
