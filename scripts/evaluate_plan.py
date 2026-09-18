#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kosmohak.loading import AssumptionsLoader, CaseDataLoader, PlanLoader, ScenarioLoader
from kosmohak.reporting import export_comparison, export_result, format_result
from kosmohak.simulation import simulate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate an immutable participant supply plan")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--scenario", default="BASE", choices=("BASE", "MANDATORY_STRESS", "both", "base", "mandatory_stress"))
    parser.add_argument("--case-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--assumptions", type=Path, default=PROJECT_ROOT / "configs/model_assumptions.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case_data = CaseDataLoader.load(args.case_root)
    assumptions = AssumptionsLoader.load(args.assumptions)
    plan = PlanLoader.load(args.plan, case_data, assumptions)
    requested = args.scenario.upper()
    scenario_ids = ("BASE", "MANDATORY_STRESS") if requested == "BOTH" else (requested,)
    results = {}
    for scenario_id in scenario_ids:
        scenario = ScenarioLoader.load(scenario_id, args.case_root)
        result = simulate(plan, scenario, case_data, assumptions)
        results[scenario_id] = result
        directory = args.output_dir / plan.plan_id / scenario_id
        export_result(result, directory, args.case_root)
        print(format_result(result))
        print(f"\nSaved: {directory}\n")
    if requested == "BOTH":
        directory = args.output_dir / plan.plan_id
        export_comparison(results["BASE"], results["MANDATORY_STRESS"], directory)
        print(f"Comparison saved: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

