import pytest


def test_zbo_transition_changes_storage_and_opex(base_result):
    december = next(row for row in base_result.monthly if row["month"] == "2035-12")
    january = next(row for row in base_result.monthly if row["month"] == "2036-01")
    assert december["active_storage_id"] == "BASE"
    assert december["active_storage_capacity_t"] == 70
    assert january["active_storage_id"] == "ZBO"
    assert january["active_storage_capacity_t"] == 120
    assert january["active_loss_rate"] == pytest.approx(0.012)
    assert january["fixed_opex_mln"] >= 1


def test_earth_new_is_unavailable_then_active(base_result):
    january = next(row for row in base_result.monthly if row["month"] == "2037-01")
    february = next(row for row in base_result.monthly if row["month"] == "2037-02")
    assert "EARTH_NEW" not in january["active_investments"]
    assert "EARTH_NEW" in february["active_investments"]
    assert february["actual_delivered_by_source"]["C"] > 0


def test_capex_components_are_not_double_counted(base_result):
    through_2036 = sum(row["capex_mln"] for row in base_result.annual if row["year"] <= 2036)
    assert through_2036 == pytest.approx(90 + 270 + 1250 + 180)
    assert not any(item.code.startswith("CAPEX_") for item in base_result.violations)

