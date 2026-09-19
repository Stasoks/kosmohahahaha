"""Reproducibility of the core engine: same inputs, same identifiers."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from kosmohak.service import evaluate_plan

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.kernel


def test_repeated_evaluation_is_deterministic(plan, base_scenario, case_data, assumptions):
    first = evaluate_plan(plan, base_scenario, case_data, assumptions)
    second = evaluate_plan(plan, base_scenario, case_data, assumptions)

    assert first.summary["run_id"] == second.summary["run_id"]
    assert first.to_dict() == second.to_dict()


def test_run_id_is_stable_across_processes(plan, base_scenario, case_data, assumptions):
    expected = evaluate_plan(plan, base_scenario, case_data, assumptions).summary["run_id"]

    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from kosmohak.loading import CaseDataLoader, AssumptionsLoader, PlanLoader, ScenarioLoader
        from kosmohak.service import evaluate_plan

        root = Path(sys.argv[1])
        case_data = CaseDataLoader.load(root)
        assumptions = AssumptionsLoader.load(root / "configs" / "model_assumptions.json")
        plan = PlanLoader.load(root / "configs" / "operator_plan_example.json", case_data, assumptions)
        base = ScenarioLoader.load("BASE", root)
        print(evaluate_plan(plan, base, case_data, assumptions).summary["run_id"])
        """
    )

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    completed = subprocess.run(
        [sys.executable, "-c", script, str(ROOT)],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    assert completed.stdout.strip() == expected
