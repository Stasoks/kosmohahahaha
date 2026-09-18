from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from kosmohak.loading import AssumptionsLoader, CaseDataLoader, PlanLoader, ScenarioLoader
from kosmohak.simulation import simulate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def case_data():
    return CaseDataLoader.load(ROOT)


@pytest.fixture(scope="session")
def assumptions():
    return AssumptionsLoader.load(ROOT / "configs/model_assumptions.json")


@pytest.fixture(scope="session")
def plan(case_data, assumptions):
    return PlanLoader.load(ROOT / "configs/operator_plan_example.json", case_data, assumptions)


@pytest.fixture(scope="session")
def base_scenario():
    return ScenarioLoader.load("BASE", ROOT)


@pytest.fixture(scope="session")
def stress_scenario():
    return ScenarioLoader.load("MANDATORY_STRESS", ROOT)


@pytest.fixture(scope="session")
def base_result(plan, base_scenario, case_data, assumptions):
    return simulate(plan, base_scenario, case_data, assumptions)


@pytest.fixture(scope="session")
def stress_result(plan, stress_scenario, case_data, assumptions):
    return simulate(plan, stress_scenario, case_data, assumptions)


def modified_plan(tmp_path, case_data, assumptions, mutate):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return PlanLoader.load(path, case_data, assumptions)

