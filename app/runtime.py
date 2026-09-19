"""Streamlit caching boundary for deterministic backend calls."""
from __future__ import annotations

import json
from typing import Any

import streamlit as st

from app import kernel_bridge as bridge


@st.cache_resource(show_spinner=False)
def context():
    return bridge.application_context()


@st.cache_data(show_spinner=False)
def _evaluate(payload: str) -> dict[str, Any]:
    return bridge.evaluate(json.loads(payload))


def evaluate(raw: dict[str, Any]) -> dict[str, Any]:
    return _evaluate(bridge.canonical_json(raw))


@st.cache_data(show_spinner=False)
def _abc(base_payload: str, stress_payload: str | None) -> dict[str, Any]:
    return bridge.abc_results(
        json.loads(base_payload),
        json.loads(stress_payload) if stress_payload else None,
    )


def abc(base_raw: dict[str, Any], stress_raw: dict[str, Any] | None) -> dict[str, Any]:
    return _abc(
        bridge.canonical_json(base_raw),
        bridge.canonical_json(stress_raw) if stress_raw else None,
    )


@st.cache_data(show_spinner=False)
def _alternatives(payload: str) -> dict[str, Any]:
    return bridge.compare_available_plans(json.loads(payload))


def alternatives(raw: dict[str, Any]) -> dict[str, Any]:
    return _alternatives(bridge.canonical_json(raw))


@st.cache_data(show_spinner=False)
def _risks(payload: str) -> dict[str, Any]:
    return bridge.risks(json.loads(payload))


def risks(raw: dict[str, Any]) -> dict[str, Any]:
    return _risks(bridge.canonical_json(raw))


@st.cache_data(show_spinner=False)
def _risk_detail(payload: str, risk_id: str) -> dict[str, Any]:
    return bridge.risk_detail(json.loads(payload), risk_id)


def risk_detail(raw: dict[str, Any], risk_id: str) -> dict[str, Any]:
    return _risk_detail(bridge.canonical_json(raw), risk_id)


@st.cache_data(show_spinner=False)
def _mitigation(payload: str, risk_id: str) -> dict[str, Any]:
    return bridge.mitigation_detail(json.loads(payload), risk_id)


def mitigation(raw: dict[str, Any], risk_id: str) -> dict[str, Any]:
    return _mitigation(bridge.canonical_json(raw), risk_id)


@st.cache_data(show_spinner=False)
def _sensitivity(payload: str, parameter_payload: str, values: tuple[Any, ...]) -> dict[str, Any]:
    parameter = json.loads(parameter_payload)
    return bridge.sensitivity(json.loads(payload), values, parameter)


def sensitivity(raw: dict[str, Any], parameter: str | dict[str, Any], values: list[Any]) -> dict[str, Any]:
    return _sensitivity(
        bridge.canonical_json(raw), bridge.canonical_json(parameter), tuple(values)
    )


@st.cache_data(show_spinner=False)
def _official_sensitivity(payload: str) -> dict[str, Any]:
    return bridge.official_demand_sensitivity(json.loads(payload))


def official_sensitivity(raw: dict[str, Any]) -> dict[str, Any]:
    return _official_sensitivity(bridge.canonical_json(raw))


@st.cache_data(show_spinner=False)
def _reverse(
    payload: str,
    parameter_payload: str,
    start: float,
    stop: float,
    step: float,
) -> dict[str, Any]:
    return bridge.reverse_stress(
        json.loads(payload),
        start,
        stop,
        step,
        parameter=json.loads(parameter_payload),
    )


def reverse(
    raw: dict[str, Any],
    parameter: str | dict[str, Any],
    start: float,
    stop: float,
    step: float,
) -> dict[str, Any]:
    return _reverse(
        bridge.canonical_json(raw),
        bridge.canonical_json(parameter),
        start,
        stop,
        step,
    )


@st.cache_data(show_spinner=False)
def builder(max_candidates: int, beam_width: int, iterations: int, seed: int) -> dict[str, Any]:
    return bridge.build_stress_specific(
        max_candidates=max_candidates,
        beam_width=beam_width,
        max_iterations=iterations,
        seed=seed,
    )


@st.cache_data(show_spinner=False)
def _workspace_evaluate(plan_payload: str, workspace_payload: str) -> dict[str, Any]:
    return bridge.evaluate_workspace(json.loads(plan_payload), json.loads(workspace_payload))


def workspace_evaluate(plan: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    return _workspace_evaluate(bridge.canonical_json(plan), bridge.canonical_json(workspace))


@st.cache_data(show_spinner=False)
def _csv(payload: str) -> dict[str, bytes]:
    return bridge.result_csv_bytes(json.loads(payload))


def csv_files(raw: dict[str, Any]) -> dict[str, bytes]:
    return _csv(bridge.canonical_json(raw))


@st.cache_data(show_spinner=False)
def _bundle(payload: str) -> bytes:
    return bridge.bundle_bytes(json.loads(payload))


def bundle(raw: dict[str, Any]) -> bytes:
    return _bundle(bridge.canonical_json(raw))
