from __future__ import annotations

from kosmohak.loading import RiskLoader
from kosmohak.risk import evaluate_risk


def test_plan_reference_mitigation_uses_saved_contingency(
    plan,
    case_data,
    assumptions,
    base_scenario,
):
    risk = RiskLoader.from_dict(
        {
            "risk_id": "TEST-PLAN-REFERENCE",
            "name": "Referenced contingency",
            "event": "Earth-Flex receives one additional month of lead time",
            "cause": "test fixture",
            "period_start": "2037-01",
            "period_end": "2039-12",
            "affected_parameters": ["additional_lead_time_months"],
            "factor_changes": [
                {
                    "factor": "additional_lead_time_months",
                    "source_id": "B",
                    "value": 1,
                    "status": "TEAM_ASSUMPTION",
                }
            ],
            "owner": "test",
            "likelihood": {"likelihood_type": "unknown"},
            "mitigation": {
                "mitigation_id": "TEST-REFERENCE",
                "description": "Use an explicit saved contingency plan.",
                "plan_reference": "plans/resilient.json",
            },
            "metadata": {"status": "TEAM_ASSUMPTION"},
        }
    )

    evaluation = evaluate_risk(
        plan,
        base_scenario,
        risk,
        case_data,
        assumptions,
    )

    mitigation = evaluation.mitigation
    assert mitigation is not None
    assert mitigation.mitigated_plan_id.endswith("--mitigation-TEST-REFERENCE")
    assert (
        mitigation.mitigated_plan["metadata"]["mitigation_plan_reference"]
        == "plans/resilient.json"
    )
    assert mitigation.mitigated_plan["metadata"]["mitigation_of"] == plan.plan_id
    assert mitigation.risk_result.summary["scenario_id"] == "BASE+TEST-PLAN-REFERENCE"
    assert mitigation.risk_result.summary["risk_ids"] == ["TEST-PLAN-REFERENCE"]
