from pathlib import Path

from kosmohak.loading import CaseDataLoader, ScenarioLoader


ROOT = Path(__file__).resolve().parents[2]


def test_case_loader_uses_official_csv_and_ids(case_data):
    assert set(case_data.sources) == {"A", "B", "C", "D", "E"}
    assert case_data.sources["E"].lead_time_unit == "week"
    assert case_data.sources["E"].lead_time_min_value == 6
    assert case_data.demand[2035].base_total_t == 100
    assert not (ROOT / "data/case_data.json").exists()


def test_official_scenarios_are_loaded_from_yaml():
    base = ScenarioLoader.load("BASE", ROOT)
    stress = ScenarioLoader.load("MANDATORY_STRESS", ROOT)
    assert base.source_path.name == "base.yaml"
    assert stress.source_path.name == "mandatory_stress.yaml"
    assert stress.demand_multiplier(2038) == 1.15
    assert stress.variable_price_multiplier("Earth-Core", 2039) == 1.25
    assert stress.actual_delivery_share("Lunar-ISRU", 2038) == 0.55


def test_official_case_loader_is_reproducible():
    first = CaseDataLoader.load(ROOT)
    second = CaseDataLoader.load(ROOT)
    assert first == second

