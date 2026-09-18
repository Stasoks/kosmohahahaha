import json
from pathlib import Path

import pytest

from kosmohak.loading import PlanLoader, PlanValidationError


ROOT = Path(__file__).resolve().parents[2]


def _invalid(tmp_path, mutate, case_data, assumptions):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return lambda: PlanLoader.load(path, case_data, assumptions)


def test_negative_order_rejected(tmp_path, case_data, assumptions):
    call = _invalid(tmp_path, lambda raw: raw["decisions"]["supply_orders"][0]["values"].update({"2035": -1}), case_data, assumptions)
    with pytest.raises(PlanValidationError, match="Negative order"):
        call()


def test_exercise_before_purchase_rejected(tmp_path, case_data, assumptions):
    def mutate(raw):
        decision = next(item for item in raw["decisions"]["investments"] if item["investment_id"] == "EARTH_NEW")
        decision["option_purchase_month"] = "2035-03"
    call = _invalid(tmp_path, mutate, case_data, assumptions)
    with pytest.raises(PlanValidationError, match="after option purchase"):
        call()


def test_late_isru_funding_rejected(tmp_path, case_data, assumptions):
    def mutate(raw):
        decision = next(item for item in raw["decisions"]["investments"] if item["investment_id"] == "LUNAR_ISRU")
        decision["funding_month"] = "2038-01"
    call = _invalid(tmp_path, mutate, case_data, assumptions)
    with pytest.raises(PlanValidationError, match="before 2038"):
        call()

