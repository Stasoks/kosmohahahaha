#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kosmohak.loading import AssumptionsLoader, CaseDataLoader, PlanLoader, ScenarioLoader
from kosmohak.reporting import export_result
from kosmohak.simulation import simulate
from kosmohak.workspace import load_workspace


def main() -> int:
    official = CaseDataLoader.load(PROJECT_ROOT)
    workspace = load_workspace(PROJECT_ROOT / "configs/research_workspace_example.json", official)
    case_data = workspace.build()
    assumptions = AssumptionsLoader.load(PROJECT_ROOT / "configs/model_assumptions.json")
    plan = PlanLoader.load(PROJECT_ROOT / "plans/research_f_2041.json", case_data, assumptions)
    scenario = ScenarioLoader.load("BASE", PROJECT_ROOT)
    result = simulate(plan, scenario, case_data, assumptions)
    directory = export_result(result, PROJECT_ROOT / "results/research-f-2041/BASE", PROJECT_ROOT)
    print(
        f"months={len(result.monthly)} valid={result.summary['valid']} "
        f"shortage={result.summary['total_shortage_t']:.3f} "
        f"cost={result.summary['undiscounted_cost_mln']:.3f} "
        f"run_id={result.summary['run_id']}"
    )
    print(f"Saved: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
