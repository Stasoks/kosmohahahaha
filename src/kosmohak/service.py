"""Stable in-process backend facade for UI clients.

The UI should import this module instead of depending on the internal loading,
simulation, risk, optimization, workspace, and reporting packages.
"""

from __future__ import annotations

import copy
import json
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.builder import StrategyBuilderConfig, StrategyBuilderResult, build_strategies
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import SimulationResult
from kosmohak.domain.risk import (
    MitigationEvaluation,
    RiskDefinition,
    RiskEvaluation,
    RiskPortfolioResult,
)
from kosmohak.domain.scenario import Scenario
from kosmohak.loading import (
    AssumptionsLoader,
    CaseDataLoader,
    PlanLoader,
    PlanValidationError,
    RiskLoader,
    RiskValidationError,
    ScenarioLoader,
)
from kosmohak.loading.case import CaseDataError
from kosmohak.optimization import (
    DecisionLocks,
    OptimizationResult,
    OptimizerConfig,
    SuggestedPlan,
    apply_plan_patch,
    explore_alternatives,
    improve_plan,
    improve_resilience,
    repair_plan,
    save_optimization_result,
)
from kosmohak.reporting import (
    export_comparison,
    export_result,
    export_risk_portfolio,
)
from kosmohak.reporting.export import build_comparison
from kosmohak.risk import (
    evaluate_mitigation,
    evaluate_risk,
    evaluate_risk_set,
    find_failure_threshold,
    official_demand_sensitivity,
    sensitivity_sweep,
)
from kosmohak.risk.reverse_stress import ReverseStressResult
from kosmohak.risk.sensitivity import SensitivityResult
from kosmohak.simulation.engine import simulate
from kosmohak.workspace import (
    CaseWorkspace,
    FutureYearSpec,
    ResearchSourceSpec,
    effective_case_to_dict,
    load_workspace,
    save_workspace,
)


UI_BACKEND_API_VERSION = "1.0"


@dataclass(frozen=True)
class ServiceError:
    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    plan: OperatorPlan | None
    errors: list[ServiceError]


@dataclass(frozen=True)
class ApplicationContext:
    root: Path
    case_data: CaseData
    assumptions: ModelAssumptions
    base_scenario: Scenario
    stress_scenario: Scenario
    risks: tuple[RiskDefinition, ...]
    stakeholders: dict[str, Any] | None
    optional_config_errors: tuple[ServiceError, ...] = ()


def to_service_error(exc: Exception) -> ServiceError:
    """Convert a known backend exception to a small UI-facing error value."""
    if isinstance(exc, PlanValidationError):
        code = "PLAN_VALIDATION_ERROR"
    elif isinstance(exc, RiskValidationError):
        code = "RISK_VALIDATION_ERROR"
    elif isinstance(exc, CaseDataError):
        code = "CASE_DATA_ERROR"
    elif isinstance(exc, FileNotFoundError):
        code = "FILE_NOT_FOUND"
    elif isinstance(exc, json.JSONDecodeError):
        code = "INVALID_JSON"
    elif isinstance(exc, ValueError):
        code = "VALUE_ERROR"
    else:
        code = "UNEXPECTED_ERROR"
    details = copy.deepcopy(getattr(exc, "details", None))
    if details is None:
        details = {"exception_type": type(exc).__name__}
    return ServiceError(
        code=code,
        message=str(exc),
        field=getattr(exc, "field", None),
        details=details,
    )


def load_application_context(root: str | Path) -> ApplicationContext:
    """Load official inputs and optional participant analysis configuration."""
    application_root = Path(root).resolve()
    case_data = CaseDataLoader.load(application_root)
    assumptions = AssumptionsLoader.load(
        application_root / "configs" / "model_assumptions.json"
    )
    base_scenario = ScenarioLoader.load("BASE", application_root)
    stress_scenario = ScenarioLoader.load("MANDATORY_STRESS", application_root)

    optional_errors: list[ServiceError] = []
    risk_path = application_root / "configs" / "risks" / "team_risks.json"
    risks: tuple[RiskDefinition, ...] = ()
    if risk_path.is_file():
        try:
            risks = tuple(RiskLoader.load(risk_path))
        except (OSError, ValueError) as exc:
            error = to_service_error(exc)
            optional_errors.append(
                ServiceError(
                    error.code,
                    error.message,
                    field="risks",
                    details={**(error.details or {}), "path": str(risk_path)},
                )
            )
    else:
        optional_errors.append(
            ServiceError(
                "OPTIONAL_CONFIG_MISSING",
                "Team risk portfolio is not configured.",
                field="risks",
                details={"path": str(risk_path)},
            )
        )

    stakeholder_path = application_root / "configs" / "stakeholders.json"
    stakeholders: dict[str, Any] | None = None
    if stakeholder_path.is_file():
        try:
            loaded = json.loads(stakeholder_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Stakeholder config must be a JSON object")
            if not isinstance(loaded.get("participants"), list):
                raise ValueError("Stakeholder config must contain a participants array")
            stakeholders = loaded
        except (OSError, ValueError) as exc:
            error = to_service_error(exc)
            optional_errors.append(
                ServiceError(
                    error.code,
                    error.message,
                    field="stakeholders",
                    details={**(error.details or {}), "path": str(stakeholder_path)},
                )
            )
    else:
        optional_errors.append(
            ServiceError(
                "OPTIONAL_CONFIG_MISSING",
                "Stakeholder config is not configured.",
                field="stakeholders",
                details={"path": str(stakeholder_path)},
            )
        )

    return ApplicationContext(
        root=application_root,
        case_data=case_data,
        assumptions=assumptions,
        base_scenario=base_scenario,
        stress_scenario=stress_scenario,
        risks=risks,
        stakeholders=stakeholders,
        optional_config_errors=tuple(optional_errors),
    )


def build_plan(
    raw: dict[str, Any],
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> OperatorPlan:
    return PlanLoader.from_dict(raw, case_data, assumptions)


def load_plan(
    path: str | Path,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> OperatorPlan:
    return PlanLoader.load(path, case_data, assumptions)


def save_plan(plan: OperatorPlan, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plan.raw, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def validate_plan(
    raw_or_plan: dict[str, Any] | OperatorPlan,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> ValidationResult:
    try:
        if isinstance(raw_or_plan, OperatorPlan):
            PlanLoader.validate(raw_or_plan, case_data, assumptions)
            plan = raw_or_plan
        else:
            plan = build_plan(raw_or_plan, case_data, assumptions)
    except (PlanValidationError, TypeError, ValueError) as exc:
        return ValidationResult(False, None, [to_service_error(exc)])
    return ValidationResult(True, plan, [])


def evaluate_plan(
    plan: OperatorPlan,
    environment: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SimulationResult:
    return simulate(plan, environment, case_data, assumptions)


def evaluate_both_scenarios(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> dict[str, Any]:
    base = simulate(plan, base_scenario, case_data, assumptions)
    stress = simulate(plan, stress_scenario, case_data, assumptions)
    return {
        "BASE": base,
        "MANDATORY_STRESS": stress,
        "comparison": build_comparison(base, stress),
    }


def compare_plans(
    plans: Iterable[OperatorPlan],
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    risks: Iterable[RiskDefinition] | None = None,
) -> dict[str, Any]:
    rows = []
    results = {}
    for plan in plans:
        pair = evaluate_both_scenarios(
            plan, base_scenario, stress_scenario, case_data, assumptions
        )
        results[plan.plan_id] = pair
        base, stress = pair["BASE"], pair["MANDATORY_STRESS"]
        source_mix = {
            source_id: sum(
                row["gross_delivery_t"]
                for row in base.sources
                if row["source_id"] == source_id
            )
            for source_id in case_data.sources
        }
        risk_consequences = []
        if risks:
            portfolio = evaluate_risk_set(
                plan, base_scenario, risks, case_data, assumptions
            )
            risk_consequences = [
                {
                    "risk_id": item.risk.risk_id,
                    "impact_score": item.impact["impact_score"],
                    "likelihood_score": item.likelihood_score,
                    "cost_delta_mln": item.consequence["delta"]["costs"][
                        "total_cost_mln"
                    ],
                    "shortage_delta_t": item.consequence["delta"][
                        "total_shortage_t"
                    ],
                    "critical_shortage_delta_t": item.consequence["delta"][
                        "critical_shortage_t"
                    ],
                }
                for item in portfolio.evaluations
            ]
        rows.append(
            {
                "plan_id": plan.plan_id,
                "base_valid": base.summary["valid"],
                "base_cost_mln": base.summary["undiscounted_cost_mln"],
                "base_cost_per_served_ton_mln": base.summary[
                    "cost_per_served_ton_mln"
                ],
                "base_service": base.summary["total_service_level"],
                "base_shortage_t": base.summary["total_shortage_t"],
                "base_minimum_inventory_t": base.summary["minimum_inventory_t"],
                "base_capex_mln": sum(row["capex_mln"] for row in base.annual),
                "stress_service": stress.summary["total_service_level"],
                "stress_shortage_t": stress.summary["total_shortage_t"],
                "stress_critical_shortage_t": stress.summary[
                    "critical_shortage_t"
                ],
                "stress_minimum_inventory_t": stress.summary[
                    "minimum_inventory_t"
                ],
                "source_mix_t": source_mix,
                "risk_consequences": risk_consequences,
            }
        )
    return {
        "status": "DIGITAL_TWIN_RESULT",
        "winner_selected": False,
        "plans": rows,
        "results": results,
    }


def evaluate_single_risk(
    plan: OperatorPlan,
    base_scenario: Scenario,
    risk: RiskDefinition,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any] | str | Path | None = None,
) -> RiskEvaluation:
    return evaluate_risk(plan, base_scenario, risk, case_data, assumptions, scoring)


def evaluate_risks(
    plan: OperatorPlan,
    base_scenario: Scenario,
    risks: Iterable[RiskDefinition],
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any] | str | Path | None = None,
) -> RiskPortfolioResult:
    return evaluate_risk_set(
        plan, base_scenario, risks, case_data, assumptions, scoring
    )


def evaluate_risk_mitigation(
    original_plan: OperatorPlan,
    base_scenario: Scenario,
    risk: RiskDefinition,
    mitigation: dict[str, Any],
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any] | str | Path | None = None,
    *,
    original_evaluation: RiskEvaluation | None = None,
) -> MitigationEvaluation:
    return evaluate_mitigation(
        original_plan,
        base_scenario,
        risk,
        mitigation,
        case_data,
        assumptions,
        scoring,
        original_evaluation=original_evaluation,
    )


def run_sensitivity(
    plan: OperatorPlan,
    parameter: str | dict[str, Any],
    values: Iterable[Any],
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SensitivityResult:
    return sensitivity_sweep(
        plan, parameter, values, base_scenario, case_data, assumptions
    )


def run_official_demand_sensitivity(
    plan: OperatorPlan,
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SensitivityResult:
    return official_demand_sensitivity(
        plan, base_scenario, case_data, assumptions
    )


def run_reverse_stress(
    plan: OperatorPlan,
    parameter: str | dict[str, Any],
    search_range: dict[str, Any],
    target_constraint: str | dict[str, Any],
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> ReverseStressResult:
    return find_failure_threshold(
        plan,
        parameter,
        search_range,
        target_constraint,
        base_scenario,
        case_data,
        assumptions,
    )


def synthesize_strategy(
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    config: StrategyBuilderConfig | None = None,
) -> StrategyBuilderResult:
    """Build a standard plan or a separate mandatory-stress adaptation.\n\n    BASE_PLAN returns plans valid under official BASE hard constraints.\n    STRESS_ADAPTATION returns plans valid under MANDATORY_STRESS hard\n    constraints while reporting 97%/99% service as resilience benchmarks.\n    Unlike Strategy Advisor, no existing OperatorPlan is required. Every\n    candidate is evaluated by the normal digital twin.\n    """    return build_strategies(
        base_scenario=base_scenario,
        stress_scenario=stress_scenario,
        case_data=case_data,
        assumptions=assumptions,
        config=config,
    )


def repair_strategy(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    locks: DecisionLocks | None = None,
    config: OptimizerConfig | None = None,
) -> OptimizationResult:
    return repair_plan(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        locks=locks,
        config=config,
    )


def improve_strategy(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    locks: DecisionLocks | None = None,
    config: OptimizerConfig | None = None,
) -> OptimizationResult:
    return improve_plan(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        locks=locks,
        config=config,
    )


def improve_strategy_resilience(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    locks: DecisionLocks | None = None,
    config: OptimizerConfig | None = None,
) -> OptimizationResult:
    return improve_resilience(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        locks=locks,
        config=config,
    )


def explore_strategy_alternatives(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    locks: DecisionLocks | None = None,
    config: OptimizerConfig | None = None,
) -> OptimizationResult:
    return explore_alternatives(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        locks=locks,
        config=config,
    )


def apply_strategy_suggestion(
    original_plan: OperatorPlan,
    suggestion: SuggestedPlan,
    *,
    new_plan_id: str,
) -> OperatorPlan:
    if not new_plan_id.strip():
        raise ValueError("new_plan_id must not be empty")
    if suggestion.base_plan_id != original_plan.plan_id:
        raise ValueError(
            "Suggestion belongs to a different original plan: "
            f"{suggestion.base_plan_id!r}"
        )
    raw = apply_plan_patch(original_plan, suggestion.patch, plan_id=new_plan_id)
    applied = OperatorPlan.from_dict(raw)
    if applied.raw["decisions"] != suggestion.resulting_plan.raw["decisions"]:
        raise RuntimeError("Suggestion patch does not reproduce its resulting decisions")
    return applied


def create_workspace(case_data: CaseData) -> CaseWorkspace:
    return CaseWorkspace.from_official(case_data)


def add_workspace_source(
    workspace: CaseWorkspace,
    spec: ResearchSourceSpec,
) -> CaseWorkspace:
    return workspace.add_source(spec)


def extend_workspace_horizon(
    workspace: CaseWorkspace,
    specs: FutureYearSpec | Iterable[FutureYearSpec],
) -> CaseWorkspace:
    return workspace.extend_horizon(specs)


def build_effective_case(workspace: CaseWorkspace) -> CaseData:
    return workspace.build()


def save_case_workspace(workspace: CaseWorkspace, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return save_workspace(workspace, target)


def load_case_workspace(
    path: str | Path,
    official_case: CaseData,
) -> CaseWorkspace:
    return load_workspace(path, official_case)


def build_research_source_spec(raw: dict[str, Any]) -> ResearchSourceSpec:
    try:
        return ResearchSourceSpec.from_dict(copy.deepcopy(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid research source specification: {exc}") from exc


def build_future_year_spec(raw: dict[str, Any]) -> FutureYearSpec:
    try:
        return FutureYearSpec.from_dict(copy.deepcopy(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid future year specification: {exc}") from exc


def export_plan_results(
    result: SimulationResult,
    output_dir: str | Path,
    case_root: str | Path,
) -> Path:
    return export_result(result, output_dir, case_root)


def export_scenario_comparison(
    base_result: SimulationResult,
    stress_result: SimulationResult,
    output_dir: str | Path,
) -> dict[str, Any]:
    return export_comparison(base_result, stress_result, output_dir)


def export_risk_results(
    portfolio: RiskPortfolioResult,
    output_dir: str | Path,
    case_root: str | Path,
) -> Path:
    return export_risk_portfolio(portfolio, output_dir, case_root)


def export_advisor_results(
    result: OptimizationResult,
    output_dir: str | Path,
) -> Path:
    return save_optimization_result(result, output_dir)


def result_summary(result: SimulationResult) -> dict[str, Any]:
    return copy.deepcopy(result.summary)


def violations_table(result: SimulationResult) -> list[dict[str, Any]]:
    return [item.to_dict() for item in result.violations]


def comparison_table(comparison: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"metric": metric, **copy.deepcopy(values)}
        for metric, values in comparison.get("summary", {}).items()
    ]


def build_download_bundle(
    *,
    plan: OperatorPlan,
    case_data: CaseData,
    base_result: SimulationResult,
    stress_result: SimulationResult,
    comparison: dict[str, Any] | None = None,
    risks: RiskPortfolioResult | None = None,
    workspace: CaseWorkspace | None = None,
    advisor_result: OptimizationResult | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Create a self-contained ZIP suitable for a Streamlit download button."""
    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
            archive_path = Path(handle.name)
    else:
        archive_path = Path(output_path)
        archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kosmohak-bundle-") as temporary:
        bundle_root = Path(temporary)
        save_plan(plan, bundle_root / "plan.json")
        export_result(base_result, bundle_root / "BASE", case_data.root)
        export_result(
            stress_result,
            bundle_root / "MANDATORY_STRESS",
            case_data.root,
        )
        generated_comparison = export_comparison(
            base_result, stress_result, bundle_root / "comparison"
        )
        if comparison is not None and comparison != generated_comparison:
            raise ValueError("Provided comparison does not match BASE/STRESS results")

        research_present = bool(
            case_data.workspace_provenance.get("research_source_ids")
            or case_data.workspace_provenance.get("research_extension_years")
        )
        case_directory = bundle_root / "case"
        if workspace is not None or research_present:
            case_directory.mkdir(parents=True, exist_ok=True)
        if workspace is not None:
            save_workspace(workspace, case_directory / "workspace.json")
        if workspace is not None or research_present:
            effective_path = case_directory / "effective_case.json"
            effective_path.write_text(
                json.dumps(
                    effective_case_to_dict(case_data),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        if risks is not None:
            export_risk_portfolio(risks, bundle_root / "risks", case_data.root)
        if advisor_result is not None:
            save_optimization_result(advisor_result, bundle_root / "advisor")

        files = sorted(
            path.relative_to(bundle_root).as_posix()
            for path in bundle_root.rglob("*")
            if path.is_file()
        )
        manifest = {
            "api_version": UI_BACKEND_API_VERSION,
            "plan_id": plan.plan_id,
            "run_ids": {
                "BASE": base_result.summary["run_id"],
                "MANDATORY_STRESS": stress_result.summary["run_id"],
            },
            "scenario_ids": {
                "BASE": base_result.summary["scenario_id"],
                "MANDATORY_STRESS": stress_result.summary["scenario_id"],
            },
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "research_extension_present": research_present,
            "files": [*files, "manifest.json"],
        }
        (bundle_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(bundle_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(bundle_root).as_posix())
    return archive_path


__all__ = [
    "UI_BACKEND_API_VERSION",
    "ApplicationContext",
    "ServiceError",
    "ValidationResult",
    "DecisionLocks",
    "OptimizerConfig",
    "StrategyBuilderConfig",
    "StrategyBuilderResult",
    "CaseWorkspace",
    "ResearchSourceSpec",
    "FutureYearSpec",
    "load_application_context",
    "build_plan",
    "load_plan",
    "save_plan",
    "validate_plan",
    "evaluate_plan",
    "evaluate_both_scenarios",
    "compare_plans",
    "evaluate_single_risk",
    "evaluate_risks",
    "evaluate_risk_mitigation",
    "run_sensitivity",
    "run_official_demand_sensitivity",
    "run_reverse_stress",
    "synthesize_strategy",
    "repair_strategy",
    "improve_strategy",
    "improve_strategy_resilience",
    "explore_strategy_alternatives",
    "apply_strategy_suggestion",
    "create_workspace",
    "add_workspace_source",
    "extend_workspace_horizon",
    "build_effective_case",
    "save_case_workspace",
    "load_case_workspace",
    "build_research_source_spec",
    "build_future_year_spec",
    "export_plan_results",
    "export_scenario_comparison",
    "export_risk_results",
    "export_advisor_results",
    "build_download_bundle",
    "result_summary",
    "violations_table",
    "comparison_table",
    "to_service_error",
]
