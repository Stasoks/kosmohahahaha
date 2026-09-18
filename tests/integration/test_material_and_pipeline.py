import pytest


def test_monthly_material_balance_and_nonnegative_inventory(base_result):
    for row in base_result.monthly:
        expected = (
            row["opening_inventory_t"]
            + row["delivered_for_balance_t"]
            - row["losses_t"]
            - row["served_critical_t"]
            - row["served_noncritical_t"]
        )
        assert row["closing_inventory_t"] == pytest.approx(expected)
        assert row["closing_inventory_t"] >= 0


def test_core_shipment_remains_in_pipeline_until_lead_time(base_result):
    january_2035 = next(row for row in base_result.monthly if row["month"] == "2035-01")
    assert any(item["source_id"] == "A" and item["planned_arrival_month"] == "2036-01" for item in january_2035["pipeline"])
    january_2036 = next(row for row in base_result.monthly if row["month"] == "2036-01")
    assert january_2036["actual_delivered_by_source"]["A"] == pytest.approx(10)
    assert not any(item["source_id"] == "A" and item["order_month"] == "2035-01" for item in january_2036["pipeline"])


def test_isru_delivery_lead_is_applied_after_commissioning(base_result):
    january = next(row for row in base_result.monthly if row["month"] == "2038-01")
    march = next(row for row in base_result.monthly if row["month"] == "2038-03")
    assert "D" not in january["actual_delivered_by_source"]
    assert any(item["source_id"] == "D" and item["planned_arrival_month"] == "2038-03" for item in january["pipeline"])
    assert march["actual_delivered_by_source"]["D"] > 0

