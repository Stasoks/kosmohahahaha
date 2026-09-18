from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.risk import RiskDefinition
from kosmohak.domain.scenario import Scenario
from kosmohak.loading.risk import RiskLoader
from kosmohak.simulation.engine import simulate
from kosmohak.simulation.environment import SimulationEnvironment


PARAMETER_FACTORS = {
    "demand_multiplier": "total_demand_multiplier",
    "critical_demand_multiplier": "critical_demand_multiplier",
    "price_multiplier": "variable_price_multiplier",
    "delivery_share": "actual_delivery_share",
    "source_availability": "availability_share",
    "lead_time": "lead_time_override_months",
    "lead_time_delay": "additional_lead_time_months",
    "capacity_multiplier": "source_capacity_multiplier",
    "storage_loss_rate": "storage_loss_rate_override",
    "storage_loss_multiplier": "storage_loss_rate_multiplier",
    "storage_capacity_multiplier": "storage_capacity_multiplier",
    "investment_delay": "investment_commissioning_delay_months",
}


@dataclass
class SensitivityResult:
    plan_id: str
    base_scenario_id: str
    parameter: dict[str, Any]
    points: list[dict[str, Any]]
    first_failing_point: dict[str, Any] | None
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "base_scenario_id": self.base_scenario_id,
            "parameter": self.parameter,
            "points": self.points,
            "first_failing_point": self.first_failing_point,
            "provenance": self.provenance,
        }


def _parameter_definition(parameter: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(parameter, str):
        return {"name": parameter}
    return dict(parameter)


def _factor_change(
    parameter: dict[str, Any],
    value: Any,
    case_data: CaseData,
) -> dict[str, Any]:
    name = str(parameter["name"])
    factor = str(parameter.get("factor", PARAMETER_FACTORS.get(name, name)))
    change: dict[str, Any] = {
        "factor": factor,
        "value": value,
        "period_start": str(parameter.get("period_start", case_data.start_month)),
        "period_end": str(parameter.get("period_end", case_data.end_month)),
        "status": str(parameter.get("status", "TEAM_ASSUMPTION")),
    }
    target_map = {
        "source_id": parameter.get("source_id"),
        "source_name": parameter.get("source_name"),
        "storage_id": parameter.get("storage_id"),
        "investment_id": parameter.get("investment_id"),
        "target_id": parameter.get("target_id"),
    }
    change.update({key: item for key, item in target_map.items() if item is not None})
    return change


def _synthetic_risk(
    parameter: dict[str, Any],
    value: Any,
    index: int,
    case_data: CaseData,
) -> RiskDefinition:
    name = str(parameter["name"])
    raw = {
        "risk_id": f"SENS_{name}_{index:04d}",
        "name": f"Sensitivity {name}={value}",
        "description": "Deterministic one-parameter sensitivity point.",
        "event": f"Sensitivity override for {name}",
        "cause": "Deterministic sensitivity analysis",
        "period_start": str(parameter.get("period_start", case_data.start_month)),
        "period_end": str(parameter.get("period_end", case_data.end_month)),
        "affected_parameters": [name],
        "factor_changes": [_factor_change(parameter, value, case_data)],
        "dependencies": [],
        "owner": "analysis",
        "likelihood": {"likelihood_type": "unknown"},
        "likelihood_status": "UNKNOWN",
        "source_references": [],
        "combination_policy": "apply_after_base",
        "metadata": {"status": "TEAM_ASSUMPTION", "analysis_type": "sensitivity"},
        "status": "TEAM_ASSUMPTION",
    }
    return RiskLoader.from_dict(raw)


def _point(value: Any, result) -> dict[str, Any]:
    return {
        "value": value,
        "run_id": result.summary["run_id"],
        "valid": result.summary["valid"],
        "total_demand_t": sum(row["demand_total_t"] for row in result.annual),
        "critical_demand_t": sum(row["demand_critical_t"] for row in result.annual),
        "total_cost_mln": result.summary["undiscounted_cost_mln"],
        "discounted_cost_mln": result.summary["discounted_cost_mln"],
        "total_service_level": result.summary["total_service_level"],
        "critical_service_level": result.summary["critical_service_level"],
        "total_shortage_t": result.summary["total_shortage_t"],
        "critical_shortage_t": result.summary["critical_shortage_t"],
        "minimum_inventory_t": result.summary["minimum_inventory_t"],
        "final_inventory_t": result.summary["final_inventory_t"],
        "hard_violation_count": result.summary["hard_violation_count"],
        "violations": [item.to_dict() for item in result.violations],
    }


def sensitivity_sweep(
    plan: OperatorPlan,
    parameter: str | dict[str, Any],
    values: Iterable[Any],
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SensitivityResult:
    definition = _parameter_definition(parameter)
    points: list[dict[str, Any]] = []
    first_failing = None
    for index, value in enumerate(values, start=1):
        risk = _synthetic_risk(definition, value, index, case_data)
        environment = SimulationEnvironment.with_risks(base_scenario, [risk])
        result = simulate(plan, environment, case_data, assumptions)
        point = _point(value, result)
        points.append(point)
        if first_failing is None and not point["valid"]:
            first_failing = point
    return SensitivityResult(
        plan_id=plan.plan_id,
        base_scenario_id=base_scenario.scenario_id,
        parameter=definition,
        points=points,
        first_failing_point=first_failing,
        provenance={
            "parameter_values": definition.get("status", "TEAM_ASSUMPTION"),
            "outputs": "DIGITAL_TWIN_RESULT",
            "operator_plan_mutated": False,
        },
    )


def official_demand_sensitivity(
    plan: OperatorPlan,
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SensitivityResult:
    low = {
        str(year): case_data.demand[year].low_total_t / case_data.demand[year].base_total_t
        for year in case_data.years
    }
    high = {
        str(year): case_data.demand[year].high_total_t / case_data.demand[year].base_total_t
        for year in case_data.years
    }
    values = [("LOW", low), ("BASE", {"default": 1.0}), ("HIGH", high)]
    points: list[dict[str, Any]] = []
    first_failing = None
    for index, (label, multipliers) in enumerate(values, start=1):
        raw = {
            "risk_id": f"SENS_OFFICIAL_DEMAND_{label}",
            "name": f"Official {label} demand sensitivity",
            "description": "Official total-demand sensitivity with the base critical share preserved.",
            "event": f"Official demand point {label}",
            "cause": "CASE_INPUT demand range",
            "period_start": case_data.start_month,
            "period_end": case_data.end_month,
            "affected_parameters": ["total_demand_multiplier", "critical_demand_multiplier"],
            "factor_changes": [
                {
                    "factor": "total_demand_multiplier",
                    "value": multipliers,
                    "status": "CASE_INPUT",
                },
                {
                    "factor": "critical_demand_multiplier",
                    "value": multipliers,
                    "status": "CASE_INPUT",
                },
            ],
            "dependencies": [],
            "owner": "organizer input",
            "likelihood": {"likelihood_type": "unknown"},
            "likelihood_status": "UNKNOWN",
            "source_references": ["data/demand.csv"],
            "combination_policy": "apply_after_base",
            "metadata": {"status": "CASE_INPUT", "analysis_type": "sensitivity"},
            "status": "CASE_INPUT",
        }
        risk = RiskLoader.from_dict(raw)
        result = simulate(
            plan,
            SimulationEnvironment.with_risks(base_scenario, [risk]),
            case_data,
            assumptions,
        )
        point = _point(label, result)
        point["multipliers_by_year"] = multipliers
        points.append(point)
        if first_failing is None and not point["valid"]:
            first_failing = point
    return SensitivityResult(
        plan_id=plan.plan_id,
        base_scenario_id=base_scenario.scenario_id,
        parameter={
            "name": "official_demand_point",
            "status": "CASE_INPUT",
            "critical_share": "preserved_from_base_year",
        },
        points=points,
        first_failing_point=first_failing,
        provenance={
            "parameter_values": "CASE_INPUT",
            "source": "data/demand.csv",
            "outputs": "DIGITAL_TWIN_RESULT",
            "operator_plan_mutated": False,
        },
    )
