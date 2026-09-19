from __future__ import annotations

import pytest

from app.kernel_bridge import (
    build_recommended_base,
    default_plan_raw,
    mitigation_detail,
)


def test_recommended_base_passes_declared_guardrails():
    result = build_recommended_base(
        max_candidates=80,
        beam_width=6,
        max_iterations=0,
        max_results=8,
        seed=17,
    )

    assert result["status"] == "success", result["candidates"]
    assert result["plan"] is not None
    selected = result["selected_candidate"]
    assert selected["base_valid"] is True
    assert selected["total_demand_guardrail_valid"] is True
    assert selected["critical_demand_guardrail_valid"] is True
    assert selected["flex_delay_guardrail_valid"] is True
    assert result["global_optimum_claimed"] is False


@pytest.mark.parametrize(
    "risk_id",
    ["R-CORE-OUTAGE", "R-ISRU-UNDERDELIVERY", "R-LOGISTICS-DELAY"],
)
def test_key_risk_mitigations_are_quantified_and_do_not_increase_shortage(risk_id):
    result = mitigation_detail(default_plan_raw(), risk_id)

    before = result["original_risk_metrics"]["total_shortage_t"]
    after = result["residual_consequence"]["risk"]["total_shortage_t"]
    assert after <= before + 1e-9
    assert result["mitigated_plan"]
    assert result["risk_result"]["summary"]["risk_ids"] == [risk_id]
