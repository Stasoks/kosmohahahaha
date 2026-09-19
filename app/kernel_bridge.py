"""Thin, testable adapter between Streamlit and the authoritative backend.

This module intentionally contains no material-balance, cost, capacity, reserve, or
service logic. It validates UI payloads, calls :mod:`kosmohak.service`, and converts
domain objects into JSON-friendly values for the presentation layer.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = ROOT / "core" if (ROOT / "core" / "src" / "kosmohak").exists() else ROOT
CORE_SRC = CORE_ROOT / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from kosmohak.service import (  # noqa: E402
    StrategyBuilderConfig,
    add_workspace_source,
    build_download_bundle,
    build_effective_case,
    build_future_year_spec,
    build_research_source_spec,
    compare_plans,
    create_workspace,
    evaluate_both_scenarios,
    evaluate_plan,
    evaluate_risk_mitigation,
    evaluate_risks,
    evaluate_single_risk,
    export_plan_results,
    export_scenario_comparison,
    extend_workspace_horizon,
    load_application_context,
    load_plan,
    run_official_demand_sensitivity,
    run_reverse_stress,
    run_sensitivity,
    synthesize_strategy,
    to_service_error,
    validate_plan,
)
from kosmohak.workspace import CaseWorkspace  # noqa: E402


class BridgeError(ValueError):
    """Structured adapter error suitable for the common UI error renderer."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.details = details or {}


@lru_cache(maxsize=1)
def application_context():
    """Load immutable official inputs once per Python process."""

    return load_application_context(CORE_ROOT)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def plan_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()[:12]


def _workspace(value: dict[str, Any] | CaseWorkspace | None) -> CaseWorkspace | None:
    if value is None:
        return None
    if isinstance(value, CaseWorkspace):
        return value
    if not isinstance(value, dict):
        raise BridgeError("WORKSPACE_TYPE_ERROR", "Workspace must be a JSON object.")
    return CaseWorkspace.from_dict(application_context().case_data, copy.deepcopy(value))


def _case_data(workspace: dict[str, Any] | CaseWorkspace | None = None):
    overlay = _workspace(workspace)
    return build_effective_case(overlay) if overlay is not None else application_context().case_data


def _error_dict(error: Any) -> dict[str, Any]:
    return {
        "code": str(getattr(error, "code", "UNEXPECTED_ERROR")),
        "message": str(getattr(error, "message", error)),
        "field": getattr(error, "field", None),
        "details": copy.deepcopy(getattr(error, "details", None)),
    }


def service_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, BridgeError):
        return {
            "code": exc.code,
            "message": str(exc),
            "field": exc.field,
            "details": copy.deepcopy(exc.details),
        }
    return _error_dict(to_service_error(exc))


def default_plan_path() -> Path:
    final = CORE_ROOT / "plans" / "final_base.json"
    return final if final.is_file() else CORE_ROOT / "configs" / "operator_plan_example.json"


def default_plan_raw() -> dict[str, Any]:
    ctx = application_context()
    return copy.deepcopy(load_plan(default_plan_path(), ctx.case_data, ctx.assumptions).raw)


def stress_reference_raw() -> dict[str, Any] | None:
    path = CORE_ROOT / "plans" / "final_stress_adaptation.json"
    if not path.is_file():
        return None
    ctx = application_context()
    return copy.deepcopy(load_plan(path, ctx.case_data, ctx.assumptions).raw)


def validate(
    raw: dict[str, Any],
    workspace: dict[str, Any] | CaseWorkspace | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    result = validate_plan(raw, _case_data(workspace), ctx.assumptions)
    return {
        "valid": result.valid,
        "errors": [_error_dict(item) for item in result.errors],
        "plan": copy.deepcopy(result.plan.raw) if result.plan is not None else None,
    }


def _validated_plan(
    raw: dict[str, Any],
    workspace: dict[str, Any] | CaseWorkspace | None = None,
):
    ctx = application_context()
    result = validate_plan(raw, _case_data(workspace), ctx.assumptions)
    if result.valid and result.plan is not None:
        return result.plan
    error = result.errors[0] if result.errors else None
    if error is None:
        raise BridgeError("PLAN_VALIDATION_ERROR", "План не прошёл структурную проверку.")
    raise BridgeError(error.code, error.message, field=error.field, details=error.details)


def evaluate(raw: dict[str, Any]) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    pair = evaluate_both_scenarios(
        plan,
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
    )
    return {
        "BASE": pair["BASE"].to_dict(),
        "MANDATORY_STRESS": pair["MANDATORY_STRESS"].to_dict(),
        "comparison": copy.deepcopy(pair["comparison"]),
        "plan_hash": plan_hash(raw),
    }


def build_stress_specific(
    *,
    max_candidates: int = 260,
    beam_width: int = 10,
    max_iterations: int = 4,
    seed: int = 17,
) -> dict[str, Any]:
    """Run the explicit bounded Builder workflow for a stress-specific plan."""

    ctx = application_context()
    result = synthesize_strategy(
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
        config=StrategyBuilderConfig(
            planning_mode="STRESS_ADAPTATION",
            objective="MIN_COST",
            max_candidates=max_candidates,
            beam_width=beam_width,
            max_iterations=max_iterations,
            max_results=1,
            seed=seed,
        ),
    )
    return result.to_dict()


def build_recommended_base(
    *,
    max_candidates: int = 1200,
    beam_width: int = 24,
    max_iterations: int = 8,
    max_results: int = 80,
    seed: int = 17,
    total_demand_guardrail: float = 1.05,
    critical_demand_guardrail: float = 1.05,
    flex_delay_guardrail_months: int = 1,
) -> dict[str, Any]:
    """Find the cheapest BASE-valid candidate that passes declared TEAM guardrails.

    Guardrails are deterministic one-factor checks and are not official CASE_INPUT
    constraints. The search remains bounded; no global optimum is claimed.
    """
    ctx = application_context()
    built = synthesize_strategy(
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
        config=StrategyBuilderConfig(
            planning_mode="BASE_PLAN",
            objective="MIN_COST",
            max_candidates=max_candidates,
            beam_width=beam_width,
            max_iterations=max_iterations,
            max_results=max_results,
            seed=seed,
            diversity_threshold=0.0,
        ),
    )
    resilience_built = synthesize_strategy(
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
        config=StrategyBuilderConfig(
            planning_mode="BASE_PLAN",
            objective="MAX_RESILIENCE",
            max_candidates=max_candidates,
            beam_width=beam_width,
            max_iterations=max_iterations,
            max_results=max_results,
            seed=seed,
            diversity_threshold=0.0,
        ),
    )

    candidates: list[tuple[Any, str]] = [
        *((solution.plan, "BUILDER_MIN_COST") for solution in built.solutions),
        *((solution.plan, "BUILDER_MAX_RESILIENCE") for solution in resilience_built.solutions),
    ]
    for name in ("cost_focused.json", "diversified.json", "resilient.json"):
        path = CORE_ROOT / "plans" / name
        if path.is_file():
            candidates.append((
                load_plan(path, ctx.case_data, ctx.assumptions),
                f"SAVED_ALTERNATIVE:{name}",
            ))

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    passing: list[tuple[float, Any, dict[str, Any]]] = []
    for plan, origin in candidates:
        decision_key = canonical_json(plan.raw.get("decisions", {}))
        if decision_key in seen:
            continue
        seen.add(decision_key)
        pair = evaluate_both_scenarios(
            plan, ctx.base_scenario, ctx.stress_scenario, ctx.case_data, ctx.assumptions
        )
        total_demand = run_sensitivity(
            plan, "demand_multiplier", [total_demand_guardrail],
            ctx.base_scenario, ctx.case_data, ctx.assumptions
        ).points[0]
        critical_demand = run_sensitivity(
            plan, "critical_demand_multiplier", [critical_demand_guardrail],
            ctx.base_scenario, ctx.case_data, ctx.assumptions
        ).points[0]
        flex_delay = run_sensitivity(
            plan,
            {"name": "lead_time_delay", "source_id": "B", "status": "TEAM_ASSUMPTION"},
            [flex_delay_guardrail_months],
            ctx.base_scenario, ctx.case_data, ctx.assumptions,
        ).points[0]
        passed = bool(
            pair["BASE"].summary["valid"]
            and total_demand["valid"]
            and critical_demand["valid"]
            and flex_delay["valid"]
        )
        row = {
            "plan_id": plan.plan_id,
            "origin": origin,
            "base_cost_mln": pair["BASE"].summary["undiscounted_cost_mln"],
            "base_valid": pair["BASE"].summary["valid"],
            "stress_service": pair["MANDATORY_STRESS"].summary["total_service_level"],
            "stress_shortage_t": pair["MANDATORY_STRESS"].summary["total_shortage_t"],
            "total_demand_guardrail_valid": total_demand["valid"],
            "critical_demand_guardrail_valid": critical_demand["valid"],
            "flex_delay_guardrail_valid": flex_delay["valid"],
            "guardrails_passed": passed,
        }
        rows.append(row)
        if passed:
            passing.append((float(row["base_cost_mln"]), plan, row))

    rows.sort(key=lambda item: (not item["guardrails_passed"], item["base_cost_mln"], item["plan_id"]))
    if not passing:
        return {
            "status": "no_guardrail_feasible_candidate_found",
            "plan": None,
            "candidates": rows,
            "builder": {
                "status": {
                    "MIN_COST": built.status,
                    "MAX_RESILIENCE": resilience_built.status,
                },
                "evaluated_candidate_count": (
                    built.evaluated_candidate_count
                    + resilience_built.evaluated_candidate_count
                ),
                "iterations": max(built.iterations, resilience_built.iterations),
            },
            "guardrails": {
                "total_demand_multiplier": total_demand_guardrail,
                "critical_demand_multiplier": critical_demand_guardrail,
                "earth_flex_additional_lead_time_months": flex_delay_guardrail_months,
                "combination": "SEPARATE_ONE_FACTOR_CHECKS",
                "status": "TEAM_ASSUMPTION",
            },
            "global_optimum_claimed": False,
        }

    passing.sort(key=lambda item: (item[0], item[1].plan_id))
    _, chosen, chosen_row = passing[0]
    raw = copy.deepcopy(chosen.raw)
    raw["plan_id"] = "recommended-base-robust"
    raw.setdefault("metadata", {}).update({
        "status": "TEAM_DECISION",
        "strategy_role": "RECOMMENDED_BASE",
        "source_candidate_plan_id": chosen.plan_id,
        "selection_rule": "minimum nominal BASE cost among candidates passing declared TEAM guardrails",
        "guardrails": {
            "total_demand_multiplier": total_demand_guardrail,
            "critical_demand_multiplier": critical_demand_guardrail,
            "earth_flex_additional_lead_time_months": flex_delay_guardrail_months,
            "combination": "SEPARATE_ONE_FACTOR_CHECKS",
            "status": "TEAM_ASSUMPTION",
        },
    })
    recommended = _validated_plan(raw)
    pair = evaluate_both_scenarios(
        recommended, ctx.base_scenario, ctx.stress_scenario, ctx.case_data, ctx.assumptions
    )
    return {
        "status": "success",
        "plan": copy.deepcopy(recommended.raw),
        "selected_candidate": chosen_row,
        "BASE": pair["BASE"].to_dict(),
        "MANDATORY_STRESS": pair["MANDATORY_STRESS"].to_dict(),
        "candidates": rows,
        "builder": {
            "status": {
                "MIN_COST": built.status,
                "MAX_RESILIENCE": resilience_built.status,
            },
            "evaluated_candidate_count": (
                built.evaluated_candidate_count
                + resilience_built.evaluated_candidate_count
            ),
            "iterations": max(built.iterations, resilience_built.iterations),
        },
        "guardrails": raw["metadata"]["guardrails"],
        "global_optimum_claimed": False,
    }

def abc_results(
    base_plan_raw: dict[str, Any],
    stress_plan_raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return A=current plan/BASE, B=same plan/STRESS, C=stress plan/STRESS."""

    pair = evaluate(base_plan_raw)
    stress_raw = stress_plan_raw or stress_reference_raw()
    if stress_raw is None:
        return {
            "A": pair["BASE"],
            "B": pair["MANDATORY_STRESS"],
            "C": None,
            "base_plan": copy.deepcopy(base_plan_raw),
            "stress_plan": None,
            "plan_hash": pair["plan_hash"],
        }
    stress_pair = evaluate(stress_raw)
    return {
        "A": pair["BASE"],
        "B": pair["MANDATORY_STRESS"],
        "C": stress_pair["MANDATORY_STRESS"],
        "base_plan": copy.deepcopy(base_plan_raw),
        "stress_plan": copy.deepcopy(stress_raw),
        "plan_hash": pair["plan_hash"],
        "stress_plan_hash": stress_pair["plan_hash"],
    }


def compare_available_plans(current_raw: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = application_context()
    paths = [
        CORE_ROOT / "plans" / "final_base.json",
        CORE_ROOT / "plans" / "cost_focused.json",
        CORE_ROOT / "plans" / "diversified.json",
        CORE_ROOT / "plans" / "resilient.json",
    ]
    plans = [load_plan(path, ctx.case_data, ctx.assumptions) for path in paths if path.is_file()]
    if current_raw is not None:
        current = _validated_plan(current_raw)
        exact_duplicate = any(
            item.plan_id == current.plan_id
            and item.raw.get("decisions") == current.raw.get("decisions")
            for item in plans
        )
        if not exact_duplicate and any(item.plan_id == current.plan_id for item in plans):
            renamed = copy.deepcopy(current.raw)
            renamed["plan_id"] = f"{current.plan_id}--current-{plan_hash(current_raw)[:6]}"
            current = _validated_plan(renamed)
        if not exact_duplicate:
            plans.append(current)
    comparison = compare_plans(
        plans,
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
    )
    return {
        "status": comparison["status"],
        "winner_selected": comparison["winner_selected"],
        "plans": copy.deepcopy(comparison["plans"]),
    }


def risks(raw: dict[str, Any]) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    result = evaluate_risks(plan, ctx.base_scenario, ctx.risks, ctx.case_data, ctx.assumptions)
    value = result.to_dict()
    value["plan_hash"] = plan_hash(raw)
    return value


def risk_catalog() -> list[dict[str, Any]]:
    return [item.to_dict() for item in application_context().risks]


def risk_detail(raw: dict[str, Any], risk_id: str) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    risk = next((item for item in ctx.risks if item.risk_id == risk_id), None)
    if risk is None:
        raise BridgeError("RISK_NOT_FOUND", f"Риск {risk_id!r} не найден.", field="risk_id")
    result = evaluate_single_risk(plan, ctx.base_scenario, risk, ctx.case_data, ctx.assumptions)
    return {
        "plan_hash": plan_hash(raw),
        "risk": risk.to_dict(),
        "register": result.to_register_entry(),
        "applied_overrides": copy.deepcopy(result.applied_overrides),
        "consequence": copy.deepcopy(result.consequence),
        "impact": copy.deepcopy(result.impact),
        "baseline": result.baseline_result.to_dict(),
        "risk_result": result.risk_result.to_dict(),
    }


def mitigation_detail(raw: dict[str, Any], risk_id: str) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    risk = next((item for item in ctx.risks if item.risk_id == risk_id), None)
    if risk is None:
        raise BridgeError("RISK_NOT_FOUND", f"Риск {risk_id!r} не найден.", field="risk_id")
    mitigation = risk.mitigation or {}
    if not (mitigation.get("plan_patch") or mitigation.get("plan_reference")):
        raise BridgeError(
            "MITIGATION_NOT_QUANTIFIED",
            "Мера описана качественно, количественный plan_patch/plan_reference не задан.",
            field="mitigation",
        )
    original = evaluate_single_risk(plan, ctx.base_scenario, risk, ctx.case_data, ctx.assumptions)
    result = evaluate_risk_mitigation(
        plan,
        ctx.base_scenario,
        risk,
        mitigation,
        ctx.case_data,
        ctx.assumptions,
        original_evaluation=original,
    )
    value = result.to_dict()
    value.update(
        {
            "plan_hash": plan_hash(raw),
            "risk_id": risk_id,
            "mitigated_plan": copy.deepcopy(result.mitigated_plan),
            "risk_result": result.risk_result.to_dict(),
            "original_risk_result": original.risk_result.to_dict(),
        }
    )
    return value


def sensitivity(
    raw: dict[str, Any],
    values: Iterable[Any],
    parameter: str | dict[str, Any] = "demand_multiplier",
) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    result = run_sensitivity(
        plan,
        parameter,
        list(values),
        ctx.base_scenario,
        ctx.case_data,
        ctx.assumptions,
    ).to_dict()
    result["plan_hash"] = plan_hash(raw)
    return result


def official_demand_sensitivity(raw: dict[str, Any]) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    result = run_official_demand_sensitivity(
        plan, ctx.base_scenario, ctx.case_data, ctx.assumptions
    ).to_dict()
    result["plan_hash"] = plan_hash(raw)
    return result


def reverse_stress(
    raw: dict[str, Any],
    start: float,
    stop: float,
    step: float,
    *,
    parameter: str | dict[str, Any] = "demand_multiplier",
    target: str | dict[str, Any] = "ANY_HARD",
) -> dict[str, Any]:
    ctx = application_context()
    plan = _validated_plan(raw)
    result = run_reverse_stress(
        plan,
        parameter,
        {"start": start, "stop": stop, "step": step},
        target,
        ctx.base_scenario,
        ctx.case_data,
        ctx.assumptions,
    ).to_dict()
    result["plan_hash"] = plan_hash(raw)
    return result


def new_workspace() -> dict[str, Any]:
    return create_workspace(application_context().case_data).to_dict()


def workspace_add_source(workspace: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    value = _workspace(workspace)
    assert value is not None
    return add_workspace_source(value, build_research_source_spec(source)).to_dict()


def workspace_extend_year(
    workspace: dict[str, Any], future_year: dict[str, Any]
) -> dict[str, Any]:
    value = _workspace(workspace)
    assert value is not None
    return extend_workspace_horizon(value, build_future_year_spec(future_year)).to_dict()


def workspace_bytes(workspace: dict[str, Any]) -> bytes:
    value = _workspace(workspace)
    assert value is not None
    return json.dumps(value.to_dict(), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def workspace_from_bytes(payload: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("INVALID_WORKSPACE_JSON", f"Некорректный workspace JSON: {exc}") from exc
    value = _workspace(raw)
    assert value is not None
    return value.to_dict()


def research_plan_template(raw: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    """Extend editable decision axes with explicit zero decisions only."""

    value = copy.deepcopy(raw)
    case_data = _case_data(workspace)
    years = [int(year) for year in case_data.years]
    schedules = {
        str(item["source_id"]): item
        for item in value.setdefault("decisions", {}).setdefault("supply_orders", [])
    }
    for source_id in case_data.sources:
        if source_id not in schedules:
            item = {"source_id": source_id, "mode": "annual_even", "values": {}}
            value["decisions"]["supply_orders"].append(item)
            schedules[source_id] = item
        schedule = schedules[source_id]
        if schedule.get("mode") == "annual_even":
            for year in years:
                schedule.setdefault("values", {}).setdefault(str(year), 0.0)
    reserve_policy = value["decisions"].setdefault("inventory_policy", {}).setdefault(
        "reserve_strategy_by_year", {}
    )
    emergency_roles = value["decisions"].setdefault("emergency_role_by_year", {})
    for year in years:
        reserve_policy.setdefault(str(year), "physical")
        emergency_roles.setdefault(str(year), "reserve_only")
    value["plan_id"] = f"{value.get('plan_id', 'plan')}-research"
    value["scenario_id"] = "BASE"
    value.setdefault("metadata", {})["research_workspace"] = "TEAM_ASSUMPTION"
    return value


def evaluate_workspace(raw: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    ctx = application_context()
    overlay = _workspace(workspace)
    assert overlay is not None
    case_data = build_effective_case(overlay)
    plan = _validated_plan(raw, overlay)
    result = evaluate_plan(plan, ctx.base_scenario, case_data, ctx.assumptions)
    return {
        "BASE": result.to_dict(),
        "plan_hash": plan_hash(raw),
        "workspace_hash": hashlib.sha256(canonical_json(workspace).encode()).hexdigest()[:12],
        "workspace": overlay.to_dict(),
        "case_metadata": case_metadata(workspace),
        "notice": (
            "MANDATORY_STRESS официально определён только для горизонта кейса; "
            "future-year assumptions имеют статус TEAM_ASSUMPTION."
        ),
    }


def case_metadata(
    workspace: dict[str, Any] | CaseWorkspace | None = None,
) -> dict[str, Any]:
    case_data = _case_data(workspace)
    return {
        "years": [int(year) for year in case_data.years],
        "official_years": [int(year) for year in case_data.official_years],
        "research_years": [int(year) for year in case_data.research_years],
        "sources": {
            source_id: copy.deepcopy(vars(source)) for source_id, source in case_data.sources.items()
        },
        "research_source_ids": list(case_data.research_source_ids),
        "demand": [copy.deepcopy(vars(case_data.demand[year])) for year in case_data.years],
        "constraints": {
            key: copy.deepcopy(vars(value)) for key, value in case_data.constraints.items()
        },
        "investments": {
            key: copy.deepcopy(vars(value)) for key, value in case_data.investments.items()
        },
        "storage": {
            key: copy.deepcopy(vars(value)) for key, value in case_data.storage.items()
        },
        "workspace_provenance": copy.deepcopy(case_data.workspace_provenance),
    }


def case_tables(
    workspace: dict[str, Any] | CaseWorkspace | None = None,
) -> dict[str, list[dict[str, Any]]]:
    metadata = case_metadata(workspace)
    return {
        "demand": metadata["demand"],
        "sources": list(metadata["sources"].values()),
        "constraints": list(metadata["constraints"].values()),
    }


def stakeholder_data() -> dict[str, Any]:
    return copy.deepcopy(application_context().stakeholders or {"participants": []})


def plan_bytes(raw: dict[str, Any]) -> bytes:
    _validated_plan(raw)
    return json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def plan_from_bytes(payload: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("INVALID_PLAN_JSON", f"Некорректный JSON плана: {exc}") from exc
    checked = validate(raw)
    if not checked["valid"]:
        error = checked["errors"][0]
        raise BridgeError(
            error["code"], error["message"], field=error["field"], details=error["details"]
        )
    return copy.deepcopy(checked["plan"])


def result_csv_bytes(raw: dict[str, Any]) -> dict[str, bytes]:
    """Use backend exporters and return portable CSV payloads for download buttons."""

    ctx = application_context()
    plan = _validated_plan(raw)
    pair = evaluate_both_scenarios(
        plan, ctx.base_scenario, ctx.stress_scenario, ctx.case_data, ctx.assumptions
    )
    files: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="kosmohak-ui-csv-") as temporary:
        root = Path(temporary)
        for scenario in ("BASE", "MANDATORY_STRESS"):
            export_plan_results(pair[scenario], root / scenario, ctx.case_data.root)
        export_scenario_comparison(
            pair["BASE"], pair["MANDATORY_STRESS"], root / "comparison"
        )
        for path in sorted(root.rglob("*.csv")):
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def bundle_bytes(
    raw: dict[str, Any], workspace: dict[str, Any] | None = None
) -> bytes:
    ctx = application_context()
    overlay = _workspace(workspace)
    case_data = build_effective_case(overlay) if overlay is not None else ctx.case_data
    plan = _validated_plan(raw, overlay)
    base_result = evaluate_plan(plan, ctx.base_scenario, case_data, ctx.assumptions)
    stress_result = evaluate_plan(plan, ctx.stress_scenario, case_data, ctx.assumptions)
    risk_result = None
    if overlay is None:
        risk_result = evaluate_risks(plan, ctx.base_scenario, ctx.risks, case_data, ctx.assumptions)
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / f"{plan.plan_id}-results.zip"
        built = build_download_bundle(
            plan=plan,
            case_data=case_data,
            base_result=base_result,
            stress_result=stress_result,
            risks=risk_result,
            workspace=overlay,
            output_path=target,
        )
        return built.read_bytes()
