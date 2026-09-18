from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.risk.sensitivity import sensitivity_sweep


@dataclass
class ReverseStressResult:
    plan_id: str
    base_scenario_id: str
    parameter: dict[str, Any]
    target_constraint: str | dict[str, Any]
    last_safe_value: Any
    first_failing_value: Any
    first_violated_constraint: dict[str, Any] | None
    period: str | None
    result_metrics: dict[str, Any] | None
    evaluated_points: list[dict[str, Any]]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "base_scenario_id": self.base_scenario_id,
            "parameter": self.parameter,
            "target_constraint": self.target_constraint,
            "last_safe_value": self.last_safe_value,
            "first_failing_value": self.first_failing_value,
            "first_violated_constraint": self.first_violated_constraint,
            "period": self.period,
            "result_metrics": self.result_metrics,
            "evaluated_points": self.evaluated_points,
            "provenance": self.provenance,
        }


def _values(search_range: dict[str, Any]) -> list[float]:
    start = Decimal(str(search_range["start"]))
    stop = Decimal(str(search_range["stop"]))
    step = Decimal(str(search_range["step"]))
    if step == 0:
        raise ValueError("Reverse-stress step cannot be zero")
    if (stop - start) * step < 0:
        raise ValueError("Reverse-stress step direction does not reach stop")
    values: list[float] = []
    current = start
    if step > 0:
        while current <= stop:
            values.append(float(current))
            current += step
    else:
        while current >= stop:
            values.append(float(current))
            current += step
    return values


def _metric(point: dict[str, Any], name: str) -> float:
    if name not in point:
        raise ValueError(f"Unknown reverse-stress metric: {name}")
    return float(point[name])


def _fails(point: dict[str, Any], target: str | dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    if isinstance(target, str):
        if target == "ANY_HARD":
            violation = next(
                (item for item in point["violations"] if item["severity"] == "hard"),
                None,
            )
            return violation is not None, violation
        violation = next(
            (
                item
                for item in point["violations"]
                if item["severity"] == "hard"
                and (item["code"] == target or item["constraint_id"] == target)
            ),
            None,
        )
        return violation is not None, violation
    metric = str(target["metric"])
    actual = _metric(point, metric)
    limit = float(target["limit"])
    operator = str(target["operator"])
    failed = actual > limit if operator == "<=" else actual < limit
    violation = None
    if failed:
        violation = {
            "code": "REVERSE_STRESS_METRIC_FAILURE",
            "constraint_id": str(target.get("constraint_id", metric)),
            "severity": "hard",
            "period": str(target.get("period", "horizon")),
            "actual": actual,
            "operator": operator,
            "limit": limit,
        }
    return failed, violation


def find_failure_threshold(
    plan: OperatorPlan,
    parameter: str | dict[str, Any],
    search_range: dict[str, Any],
    target_constraint: str | dict[str, Any],
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> ReverseStressResult:
    values = _values(search_range)
    sweep = sensitivity_sweep(
        plan,
        parameter,
        values,
        base_scenario,
        case_data,
        assumptions,
    )
    last_safe = None
    first_failing = None
    first_violation = None
    failing_point = None
    for point in sweep.points:
        failed, violation = _fails(point, target_constraint)
        if failed:
            first_failing = point["value"]
            first_violation = violation
            failing_point = point
            break
        last_safe = point["value"]
    return ReverseStressResult(
        plan_id=plan.plan_id,
        base_scenario_id=base_scenario.scenario_id,
        parameter=sweep.parameter,
        target_constraint=target_constraint,
        last_safe_value=last_safe,
        first_failing_value=first_failing,
        first_violated_constraint=first_violation,
        period=first_violation.get("period") if first_violation else None,
        result_metrics=(
            {key: value for key, value in failing_point.items() if key != "violations"}
            if failing_point
            else None
        ),
        evaluated_points=sweep.points,
        provenance={
            "search": "DETERMINISTIC_ORDERED_GRID",
            "strategy_changed": False,
            "outputs": "DIGITAL_TWIN_RESULT",
        },
    )
