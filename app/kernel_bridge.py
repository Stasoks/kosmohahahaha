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
    build_case_with_source_overrides,
    build_custom_environment,
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


def input_hash(source_overrides: dict[str, Any] | None = None) -> str:
    payload = canonical_json(source_overrides or {})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def scenario_hash(spec: dict[str, Any] | None = None) -> str:
    payload = canonical_json(spec or {})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


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


def _case_data_with_source_overrides(
    source_overrides: dict[str, dict[str, Any]] | None = None,
):
    return build_case_with_source_overrides(
        application_context().case_data,
        copy.deepcopy(source_overrides or {}),
    )


def _validated_plan_for_case(raw: dict[str, Any], case_data):
    ctx = application_context()
    result = validate_plan(raw, case_data, ctx.assumptions)
    if result.valid and result.plan is not None:
        return result.plan
    error = result.errors[0] if result.errors else None
    if error is None:
        raise BridgeError("PLAN_VALIDATION_ERROR", "План не прошёл структурную проверку.")
    raise BridgeError(error.code, error.message, field=error.field, details=error.details)


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


PLAN_PRESETS: dict[str, dict[str, str]] = {
    "final_base": {
        "label": "Финальный BASE · минимум стоимости",
        "path": "plans/final_base.json",
        "description": "Основной номинальный план для обычного сценария.",
    },
    "stress_adaptation": {
        "label": "Адаптированный под стресс",
        "path": "plans/final_stress_adaptation.json",
        "description": "Отдельный заранее подготовленный план для обязательного стресс-сценария.",
    },
    "cost_focused": {
        "label": "Альтернатива · экономичная",
        "path": "plans/cost_focused.json",
        "description": "Сравнительный вариант с акцентом на стоимость.",
    },
    "diversified": {
        "label": "Альтернатива · диверсифицированная",
        "path": "plans/diversified.json",
        "description": "Сравнительный вариант с более распределёнными поставками.",
    },
    "resilient": {
        "label": "Альтернатива · устойчивая",
        "path": "plans/resilient.json",
        "description": "Сравнительный вариант с большим запасом устойчивости.",
    },
}


def plan_presets() -> list[dict[str, str]]:
    """Return saved operator strategies available for explicit UI switching."""

    ctx = application_context()
    output: list[dict[str, str]] = []
    for key, item in PLAN_PRESETS.items():
        path = CORE_ROOT / item["path"]
        if not path.is_file():
            continue
        plan = load_plan(path, ctx.case_data, ctx.assumptions)
        output.append({
            "key": key,
            "label": item["label"],
            "description": item["description"],
            "plan_id": plan.plan_id,
            "scenario_id": plan.scenario_id,
        })
    return output


def plan_preset_raw(key: str) -> dict[str, Any]:
    """Load one saved plan without changing session state or recalculating it."""

    if key not in PLAN_PRESETS:
        raise BridgeError("UNKNOWN_PLAN_PRESET", f"Неизвестная сохранённая стратегия: {key}")
    path = CORE_ROOT / PLAN_PRESETS[key]["path"]
    if not path.is_file():
        raise BridgeError("PLAN_PRESET_NOT_FOUND", f"Файл стратегии не найден: {path.name}")
    ctx = application_context()
    return copy.deepcopy(load_plan(path, ctx.case_data, ctx.assumptions).raw)


def plan_preset_key(raw: dict[str, Any]) -> str | None:
    """Identify a saved preset by plan_id and decisions, if the current plan matches one."""

    current_id = str(raw.get("plan_id", ""))
    current_decisions = raw.get("decisions")
    for item in plan_presets():
        if item["plan_id"] != current_id:
            continue
        candidate = plan_preset_raw(item["key"])
        if candidate.get("decisions") == current_decisions:
            return item["key"]
    return None


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


def evaluate(
    raw: dict[str, Any],
    source_overrides: dict[str, dict[str, Any]] | None = None,
    custom_scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    pair = evaluate_both_scenarios(
        plan,
        ctx.base_scenario,
        ctx.stress_scenario,
        case_data,
        ctx.assumptions,
    )
    value = {
        "BASE": pair["BASE"].to_dict(),
        "MANDATORY_STRESS": pair["MANDATORY_STRESS"].to_dict(),
        "comparison": copy.deepcopy(pair["comparison"]),
        "plan_hash": plan_hash(raw),
        "input_hash": input_hash(source_overrides),
        "source_overrides": copy.deepcopy(source_overrides or {}),
    }
    if custom_scenario:
        base_key = str(custom_scenario.get("base_scenario", "BASE"))
        base_environment = (
            ctx.stress_scenario if base_key == "MANDATORY_STRESS" else ctx.base_scenario
        )
        environment = build_custom_environment(base_environment, custom_scenario)
        custom = evaluate_plan(plan, environment, case_data, ctx.assumptions)
        value["CUSTOM"] = custom.to_dict()
        value["custom_scenario"] = {
            "name": str(custom_scenario.get("name", "Пользовательский сценарий")),
            "base_scenario": base_key,
            "period_start": custom_scenario.get("period_start"),
            "period_end": custom_scenario.get("period_end"),
            "factor_changes": copy.deepcopy(custom_scenario.get("factor_changes", [])),
            "scenario_hash": scenario_hash(custom_scenario),
        }
    return value


def build_stress_specific(
    *,
    max_candidates: int = 260,
    beam_width: int = 10,
    max_iterations: int = 4,
    seed: int = 17,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the explicit bounded Builder workflow for a stress-specific plan."""

    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    result = synthesize_strategy(
        ctx.base_scenario,
        ctx.stress_scenario,
        case_data,
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


def abc_results(
    base_plan_raw: dict[str, Any],
    stress_plan_raw: dict[str, Any] | None = None,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return A=current plan/BASE, B=same plan/STRESS, C=stress plan/STRESS."""

    pair = evaluate(base_plan_raw, source_overrides)
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
    stress_pair = evaluate(stress_raw, source_overrides)
    return {
        "A": pair["BASE"],
        "B": pair["MANDATORY_STRESS"],
        "C": stress_pair["MANDATORY_STRESS"],
        "base_plan": copy.deepcopy(base_plan_raw),
        "stress_plan": copy.deepcopy(stress_raw),
        "plan_hash": pair["plan_hash"],
        "stress_plan_hash": stress_pair["plan_hash"],
    }


def compare_available_plans(
    current_raw: dict[str, Any] | None = None,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    paths = [
        CORE_ROOT / "plans" / "final_base.json",
        CORE_ROOT / "plans" / "cost_focused.json",
        CORE_ROOT / "plans" / "diversified.json",
        CORE_ROOT / "plans" / "resilient.json",
    ]
    plans = [load_plan(path, case_data, ctx.assumptions) for path in paths if path.is_file()]
    if current_raw is not None:
        current = _validated_plan_for_case(current_raw, case_data)
        exact_duplicate = any(
            item.plan_id == current.plan_id
            and item.raw.get("decisions") == current.raw.get("decisions")
            for item in plans
        )
        if not exact_duplicate and any(item.plan_id == current.plan_id for item in plans):
            renamed = copy.deepcopy(current.raw)
            renamed["plan_id"] = f"{current.plan_id}--current-{plan_hash(current_raw)[:6]}"
            current = _validated_plan_for_case(renamed, case_data)
        if not exact_duplicate:
            plans.append(current)
    comparison = compare_plans(
        plans,
        ctx.base_scenario,
        ctx.stress_scenario,
        case_data,
        ctx.assumptions,
    )
    return {
        "status": comparison["status"],
        "winner_selected": comparison["winner_selected"],
        "plans": copy.deepcopy(comparison["plans"]),
    }


def risks(
    raw: dict[str, Any],
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    result = evaluate_risks(plan, ctx.base_scenario, ctx.risks, case_data, ctx.assumptions)
    value = result.to_dict()
    value["plan_hash"] = plan_hash(raw)
    value["input_hash"] = input_hash(source_overrides)
    return value


def risk_catalog() -> list[dict[str, Any]]:
    return [item.to_dict() for item in application_context().risks]


def risk_detail(
    raw: dict[str, Any],
    risk_id: str,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    risk = next((item for item in ctx.risks if item.risk_id == risk_id), None)
    if risk is None:
        raise BridgeError("RISK_NOT_FOUND", f"Риск {risk_id!r} не найден.", field="risk_id")
    result = evaluate_single_risk(plan, ctx.base_scenario, risk, case_data, ctx.assumptions)
    return {
        "plan_hash": plan_hash(raw),
        "input_hash": input_hash(source_overrides),
        "risk": risk.to_dict(),
        "register": result.to_register_entry(),
        "applied_overrides": copy.deepcopy(result.applied_overrides),
        "consequence": copy.deepcopy(result.consequence),
        "impact": copy.deepcopy(result.impact),
        "baseline": result.baseline_result.to_dict(),
        "risk_result": result.risk_result.to_dict(),
    }


def mitigation_detail(
    raw: dict[str, Any],
    risk_id: str,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    risk = next((item for item in ctx.risks if item.risk_id == risk_id), None)
    if risk is None:
        raise BridgeError("RISK_NOT_FOUND", f"Риск {risk_id!r} не найден.", field="risk_id")
    mitigation = risk.mitigation or {}
    if not mitigation.get("plan_patch"):
        raise BridgeError(
            "MITIGATION_NOT_QUANTIFIED",
            "Мера описана качественно, количественный plan_patch не задан.",
            field="mitigation",
        )
    original = evaluate_single_risk(plan, ctx.base_scenario, risk, case_data, ctx.assumptions)
    result = evaluate_risk_mitigation(
        plan,
        ctx.base_scenario,
        risk,
        mitigation,
        case_data,
        ctx.assumptions,
        original_evaluation=original,
    )
    value = result.to_dict()
    value.update(
        {
            "plan_hash": plan_hash(raw),
            "input_hash": input_hash(source_overrides),
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
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    result = run_sensitivity(
        plan,
        parameter,
        list(values),
        ctx.base_scenario,
        case_data,
        ctx.assumptions,
    ).to_dict()
    result["plan_hash"] = plan_hash(raw)
    result["input_hash"] = input_hash(source_overrides)
    return result


def official_demand_sensitivity(
    raw: dict[str, Any],
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    result = run_official_demand_sensitivity(
        plan, ctx.base_scenario, case_data, ctx.assumptions
    ).to_dict()
    result["plan_hash"] = plan_hash(raw)
    result["input_hash"] = input_hash(source_overrides)
    return result


def reverse_stress(
    raw: dict[str, Any],
    start: float,
    stop: float,
    step: float,
    *,
    parameter: str | dict[str, Any] = "demand_multiplier",
    target: str | dict[str, Any] = "ANY_HARD",
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    result = run_reverse_stress(
        plan,
        parameter,
        {"start": start, "stop": stop, "step": step},
        target,
        ctx.base_scenario,
        case_data,
        ctx.assumptions,
    ).to_dict()
    result["plan_hash"] = plan_hash(raw)
    result["input_hash"] = input_hash(source_overrides)
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
    *,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if workspace is not None and source_overrides:
        raise BridgeError(
            "CASE_OVERLAY_CONFLICT",
            "Research workspace and source editor cannot be applied in one case_metadata call.",
        )
    case_data = (
        _case_data(workspace)
        if workspace is not None
        else _case_data_with_source_overrides(source_overrides)
    )
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
    *,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    metadata = case_metadata(workspace, source_overrides=source_overrides)
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


def result_csv_bytes(
    raw: dict[str, Any],
    source_overrides: dict[str, dict[str, Any]] | None = None,
    custom_scenario: dict[str, Any] | None = None,
) -> dict[str, bytes]:
    """Use backend exporters and return portable CSV payloads for download buttons."""

    ctx = application_context()
    case_data = _case_data_with_source_overrides(source_overrides)
    plan = _validated_plan_for_case(raw, case_data)
    pair = evaluate_both_scenarios(
        plan, ctx.base_scenario, ctx.stress_scenario, case_data, ctx.assumptions
    )
    files: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="kosmohak-ui-csv-") as temporary:
        root = Path(temporary)
        for scenario in ("BASE", "MANDATORY_STRESS"):
            export_plan_results(pair[scenario], root / scenario, case_data.root)
        export_scenario_comparison(
            pair["BASE"], pair["MANDATORY_STRESS"], root / "comparison"
        )
        if custom_scenario:
            base_key = str(custom_scenario.get("base_scenario", "BASE"))
            base_environment = (
                ctx.stress_scenario
                if base_key == "MANDATORY_STRESS"
                else ctx.base_scenario
            )
            environment = build_custom_environment(base_environment, custom_scenario)
            custom_result = evaluate_plan(plan, environment, case_data, ctx.assumptions)
            export_plan_results(custom_result, root / "CUSTOM", case_data.root)
            (root / "CUSTOM" / "scenario.json").write_text(
                json.dumps(custom_scenario, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        if source_overrides:
            (root / "source-overrides.json").write_text(
                json.dumps(source_overrides, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".csv", ".json"}:
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def bundle_bytes(
    raw: dict[str, Any],
    workspace: dict[str, Any] | None = None,
    source_overrides: dict[str, dict[str, Any]] | None = None,
) -> bytes:
    ctx = application_context()
    overlay = _workspace(workspace)
    if overlay is not None and source_overrides:
        raise BridgeError(
            "CASE_OVERLAY_CONFLICT",
            "Research workspace and source editor cannot be bundled together.",
        )
    case_data = (
        build_effective_case(overlay)
        if overlay is not None
        else _case_data_with_source_overrides(source_overrides)
    )
    plan = (
        _validated_plan(raw, overlay)
        if overlay is not None
        else _validated_plan_for_case(raw, case_data)
    )
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
