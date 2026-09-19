#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kosmohak.loading import (
    AssumptionsLoader,
    CaseDataLoader,
    PlanLoader,
    RiskLoader,
    ScenarioLoader,
)
from kosmohak.reporting import export_plan_comparison
from kosmohak.service import compare_plans


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare complete strategies without selecting a winner")
    parser.add_argument("plans", nargs="+", type=Path)
    parser.add_argument("--risks", type=Path)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results/strategy-comparison")
    args = parser.parse_args()
    case_data = CaseDataLoader.load(PROJECT_ROOT)
    assumptions = AssumptionsLoader.load(PROJECT_ROOT / "configs/model_assumptions.json")
    plans = [PlanLoader.load(path, case_data, assumptions) for path in args.plans]
    base = ScenarioLoader.load("BASE", PROJECT_ROOT)
    stress = ScenarioLoader.load("MANDATORY_STRESS", PROJECT_ROOT)
    risks = RiskLoader.load(args.risks) if args.risks else None
    comparison = compare_plans(
        plans, base, stress, case_data, assumptions, risks=risks
    )
    export_plan_comparison(comparison, args.output_dir)
    for row in comparison["plans"]:
        print(
            f"{row['plan_id']}: BASE valid={row['base_valid']} "
            f"cost={row['base_cost_mln']:.3f}; "
            f"STRESS shortage={row['stress_shortage_t']:.3f} t"
        )
    print(f"Saved: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
