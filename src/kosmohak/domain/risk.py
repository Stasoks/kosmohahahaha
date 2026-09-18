from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from kosmohak.domain.result import SimulationResult


@dataclass(frozen=True)
class RiskDefinition:
    risk_id: str
    name: str
    description: str
    event: str
    cause: str
    period_start: str
    period_end: str
    affected_parameters: tuple[str, ...]
    factor_changes: tuple[dict[str, Any], ...]
    dependencies: tuple[str, ...]
    owner: str
    likelihood: dict[str, Any]
    likelihood_basis: str | None
    likelihood_status: str
    source_references: tuple[str, ...]
    combination_policy: str
    mitigation: dict[str, Any] | None
    metadata: dict[str, Any]
    status: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("raw", None)
        return value


@dataclass
class MitigationEvaluation:
    mitigation_id: str
    mitigation_cost_mln: float
    base_original_cost_mln: float
    base_mitigated_cost_mln: float
    original_risk_metrics: dict[str, Any]
    residual_consequence: dict[str, Any]
    residual_impact: dict[str, Any]
    residual_likelihood: dict[str, Any]
    residual_likelihood_score: int | None
    residual_risk_score: int | None
    mitigated_plan_id: str
    mitigated_plan: dict[str, Any]
    risk_result: SimulationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "mitigation_id": self.mitigation_id,
            "mitigation_cost_mln": self.mitigation_cost_mln,
            "base_original_cost_mln": self.base_original_cost_mln,
            "base_mitigated_cost_mln": self.base_mitigated_cost_mln,
            "original_risk_metrics": self.original_risk_metrics,
            "residual_consequence": self.residual_consequence,
            "residual_impact": self.residual_impact,
            "residual_likelihood": self.residual_likelihood,
            "residual_likelihood_score": self.residual_likelihood_score,
            "residual_risk_score": self.residual_risk_score,
            "mitigated_plan_id": self.mitigated_plan_id,
        }


@dataclass
class RiskEvaluation:
    risk: RiskDefinition
    baseline_run_id: str
    risk_run_id: str
    base_scenario_id: str
    environment_id: str
    applied_overrides: list[dict[str, Any]]
    consequence: dict[str, Any]
    impact: dict[str, Any]
    likelihood: dict[str, Any]
    likelihood_score: int | None
    ordinal_risk_score: int | None
    baseline_result: SimulationResult
    risk_result: SimulationResult
    mitigation: MitigationEvaluation | None = None

    def to_register_entry(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk.risk_id,
            "name": self.risk.name,
            "event": self.risk.event,
            "cause": self.risk.cause,
            "period_start": self.risk.period_start,
            "period_end": self.risk.period_end,
            "affected_parameters": list(self.risk.affected_parameters),
            "dependencies": list(self.risk.dependencies),
            "owner": self.risk.owner,
            "likelihood": self.likelihood,
            "likelihood_basis": self.risk.likelihood_basis,
            "likelihood_status": self.risk.likelihood_status,
            "source_references": list(self.risk.source_references),
            "impact_score": self.impact["impact_score"],
            "impact_dimensions": self.impact["dimensions"],
            "likelihood_score": self.likelihood_score,
            "ordinal_risk_score": self.ordinal_risk_score,
            "baseline_run_id": self.baseline_run_id,
            "risk_run_id": self.risk_run_id,
            "base_scenario_id": self.base_scenario_id,
            "environment_id": self.environment_id,
            "applied_overrides": self.applied_overrides,
            "baseline_metrics": self.consequence["baseline"],
            "risk_metrics": self.consequence["risk"],
            "quantitative_delta": self.consequence["delta"],
            "first_violation": self.consequence["risk"].get("first_violation"),
            "all_violations": self.consequence["risk"].get("violations", []),
            "mitigation": self.mitigation.to_dict() if self.mitigation else self.risk.mitigation,
            "provenance": {
                "risk_definition": self.risk.status,
                "likelihood": self.risk.likelihood_status,
                "impact": "DIGITAL_TWIN_RESULT",
                "impact_run_id": self.risk_run_id,
                "impact_score": "TEAM_ASSUMPTION_SCORING_RULE",
            },
        }


@dataclass
class RiskPortfolioResult:
    plan_id: str
    base_scenario_id: str
    evaluations: list[RiskEvaluation]
    risk_register: list[dict[str, Any]]
    risk_matrix: dict[str, Any]
    unknown_likelihood_risks: list[str]
    scoring_config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "base_scenario_id": self.base_scenario_id,
            "risk_register": self.risk_register,
            "risk_matrix": self.risk_matrix,
            "unknown_likelihood_risks": self.unknown_likelihood_risks,
            "scoring_config": self.scoring_config,
        }
