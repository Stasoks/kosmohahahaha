from __future__ import annotations

import json
from pathlib import Path

import pytest

from kosmohak.constraints import capacity_violation
from kosmohak.economics.contracts import contract_cost, reservation_payment
from kosmohak.simulation.physics import (
    apply_delivery_share,
    material_balance,
    reserve_tons,
    serve_demand,
    split_demand,
    throughput_losses,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    item["case_id"]: item["expected"]
    for item in json.loads((ROOT / "validation/expected_checks.json").read_text(encoding="utf-8"))
}


def run_control_case(case_id: str) -> dict:
    if case_id == "V01":
        return {"closing_inventory_t": material_balance(10, 30, 2, 25)}
    if case_id == "V02":
        value = serve_demand(8, 10, 0)
        return {
            "served_t": value.served_critical_t + value.served_noncritical_t,
            "shortage_t": value.shortage_critical_t + value.shortage_noncritical_t,
            "closing_inventory_t": value.closing_inventory_t,
        }
    if case_id in {"V03", "V04"}:
        value = contract_cost(
            ordered_volume_t=50,
            reserved_capacity_period_t=100,
            take_or_pay_share=0.70,
            variable_price_mln_per_t=2,
            annual_reserved_capacity_t=100,
            reservation_rate_mln_per_t_year_capacity=0,
            period_fraction=1,
        )
        output = {"variable_payment_mln": value.variable_payment_mln}
        if case_id == "V03":
            output["payable_volume_t"] = value.payable_volume_t
        return output
    if case_id == "V05":
        return {"reservation_payment_mln": reservation_payment(100, 0.4, 0.5)}
    if case_id == "V06":
        return {"losses_t": throughput_losses(20, 0.05)}
    if case_id == "V07":
        return {"reserve_t": reserve_tons(365, 45)}
    if case_id == "V08":
        violation = capacity_violation(12, 10, source_id="Source-X", year=2038, scenario="SYNTHETIC")
        assert violation is not None
        return {"violation": violation.code, "excess_t": violation.excess_or_gap}
    if case_id == "V09":
        critical, noncritical = split_demand(100, 60)
        return {"total_demand_t": critical + noncritical}
    if case_id == "V10":
        return {"actual_delivery_t": apply_delivery_share(20, 0.50, reliability_metadata=0.80)}
    raise AssertionError(f"Unknown official control case: {case_id}")


@pytest.mark.parametrize("case_id", [f"V{number:02d}" for number in range(1, 11)])
def test_official_control_case(case_id):
    actual = run_control_case(case_id)
    expected = EXPECTED[case_id]
    assert actual.keys() == expected.keys()
    for key, expected_value in expected.items():
        if isinstance(expected_value, (int, float)):
            assert actual[key] == pytest.approx(expected_value)
        else:
            assert actual[key] == expected_value

