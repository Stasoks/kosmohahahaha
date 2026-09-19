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
from kosmohak.optimization import (
    OptimizerConfig,
    improve_plan,
    improve_resilience,
    repair_plan,
    save_optimization_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Strategy Advisor")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--mode", choices=("repair", "improve", "resilience"), required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    args = parser.parse_args()
    case_data = CaseDataLoader.load(PROJECT_ROOT)
    assumptions = AssumptionsLoader.load(PROJECT_ROOT / "configs/model_assumptions.json")
    plan = PlanLoader.load(args.plan, case_data, assumptions)
    base = ScenarioLoader.load("BASE", PROJECT_ROOT)
    stress = ScenarioLoader.load("MANDATORY_STRESS", PROJECT_ROOT)
    function = {
        "repair": repair_plan,
        "improve": improve_plan,
        "resilience": improve_resilience,
    }[args.mode]
    result = function(
        plan,
        base,
        stress,
        case_data,
        assumptions,
        config=OptimizerConfig(seed=args.seed, max_candidates=args.max_candidates),
    )
    directory = save_optimization_result(
        result, args.output_dir / plan.plan_id / "advisor" / args.mode
    )
    print(
        f"mode={result.mode} status={result.status} "
        f"evaluated={result.evaluated_candidates} feasible={result.feasible_candidates}"
    )
    print(f"Saved: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
