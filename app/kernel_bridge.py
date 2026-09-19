"""Thin, testable adapter between Streamlit and the supplied kosmohak kernel."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
# Local deliverable bundles the supplied kernel in ``core``.  On the GitHub
# ``web`` branch the same kernel already lives at repository root, so the UI
# reuses it without duplicating or modifying those files.
CORE_ROOT = ROOT / "core" if (ROOT / "core" / "src" / "kosmohak").exists() else ROOT
CORE_SRC = CORE_ROOT / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from kosmohak.service import (  # noqa: E402
    build_download_bundle,
    evaluate_both_scenarios,
    evaluate_risks,
    load_application_context,
    load_plan,
    run_reverse_stress,
    run_sensitivity,
    to_service_error,
    validate_plan,
)


def application_context():
    return load_application_context(CORE_ROOT)


def default_plan_raw() -> dict[str, Any]:
    ctx = application_context()
    plan = load_plan(CORE_ROOT / "configs" / "operator_plan_example.json", ctx.case_data, ctx.assumptions)
    return copy.deepcopy(plan.raw)


def plan_hash(raw: dict[str, Any]) -> str:
    payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def service_error(exc: Exception) -> dict[str, Any]:
    error = to_service_error(exc)
    return {
        "code": error.code,
        "message": error.message,
        "field": error.field,
        "details": error.details,
    }


def evaluate(raw: dict[str, Any]) -> dict[str, Any]:
    ctx = application_context()
    validation = validate_plan(raw, ctx.case_data, ctx.assumptions)
    if not validation.valid or validation.plan is None:
        error = validation.errors[0]
        raise ValueError(f"{error.code}: {error.message}")
    pair = evaluate_both_scenarios(
        validation.plan,
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
    )
    return {
        "BASE": pair["BASE"].to_dict(),
        "MANDATORY_STRESS": pair["MANDATORY_STRESS"].to_dict(),
        "comparison": pair["comparison"],
        "plan_hash": plan_hash(raw),
    }


def risks(raw: dict[str, Any]) -> dict[str, Any]:
    ctx = application_context()
    validation = validate_plan(raw, ctx.case_data, ctx.assumptions)
    if not validation.valid or validation.plan is None:
        raise ValueError(validation.errors[0].message)
    result = evaluate_risks(
        validation.plan, ctx.base_scenario, ctx.risks, ctx.case_data, ctx.assumptions
    )
    return result.to_dict()


def sensitivity(raw: dict[str, Any], values: list[float]) -> dict[str, Any]:
    ctx = application_context()
    validation = validate_plan(raw, ctx.case_data, ctx.assumptions)
    if not validation.valid or validation.plan is None:
        raise ValueError(validation.errors[0].message)
    return run_sensitivity(
        validation.plan,
        "demand_multiplier",
        values,
        ctx.base_scenario,
        ctx.case_data,
        ctx.assumptions,
    ).to_dict()


def reverse_stress(raw: dict[str, Any], start: float, stop: float, step: float) -> dict[str, Any]:
    ctx = application_context()
    validation = validate_plan(raw, ctx.case_data, ctx.assumptions)
    if not validation.valid or validation.plan is None:
        raise ValueError(validation.errors[0].message)
    return run_reverse_stress(
        validation.plan,
        "demand_multiplier",
        {"start": start, "stop": stop, "step": step},
        "ANY_HARD",
        ctx.base_scenario,
        ctx.case_data,
        ctx.assumptions,
    ).to_dict()


def bundle_bytes(raw: dict[str, Any]) -> bytes:
    ctx = application_context()
    validation = validate_plan(raw, ctx.case_data, ctx.assumptions)
    if not validation.valid or validation.plan is None:
        raise ValueError(validation.errors[0].message)
    pair = evaluate_both_scenarios(
        validation.plan,
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
    )
    risk_result = evaluate_risks(
        validation.plan, ctx.base_scenario, ctx.risks, ctx.case_data, ctx.assumptions
    )
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / f"{validation.plan.plan_id}-results.zip"
        built = build_download_bundle(
            plan=validation.plan,
            case_data=ctx.case_data,
            base_result=pair["BASE"],
            stress_result=pair["MANDATORY_STRESS"],
            comparison=pair["comparison"],
            risks=risk_result,
            output_path=target,
        )
        return built.read_bytes()


def case_tables() -> dict[str, list[dict[str, Any]]]:
    ctx = application_context()
    demand = [vars(ctx.case_data.demand[year]) for year in sorted(ctx.case_data.demand)]
    sources = [vars(source) for source in ctx.case_data.sources.values()]
    constraints = [vars(item) for item in ctx.case_data.constraints.values()]
    return {"demand": demand, "sources": sources, "constraints": constraints}
