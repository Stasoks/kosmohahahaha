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
from kosmohak.reporting import export_analysis_result
from kosmohak.risk import official_demand_sensitivity, sensitivity_sweep


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic one-factor sensitivity")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--parameter", default="demand_multiplier")
    parser.add_argument("--values", default="0.8,1.0,1.2")
    parser.add_argument("--source-id")
    parser.add_argument("--storage-id")
    parser.add_argument("--investment-id")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument("--official-demand", action="store_true")
    parser.add_argument("--scenario", default="BASE", choices=("BASE", "MANDATORY_STRESS"))
    parser.add_argument("--case-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--assumptions", type=Path, default=PROJECT_ROOT / "configs/model_assumptions.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case_data = CaseDataLoader.load(args.case_root)
    assumptions = AssumptionsLoader.load(args.assumptions)
    plan = PlanLoader.load(args.plan, case_data, assumptions)
    scenario = ScenarioLoader.load(args.scenario, args.case_root)
    if args.official_demand:
        result = official_demand_sensitivity(plan, scenario, case_data, assumptions)
        name = "official_demand"
    else:
        parameter = {
            "name": args.parameter,
            **({"source_id": args.source_id} if args.source_id else {}),
            **({"storage_id": args.storage_id} if args.storage_id else {}),
            **({"investment_id": args.investment_id} if args.investment_id else {}),
            **({"period_start": args.period_start} if args.period_start else {}),
            **({"period_end": args.period_end} if args.period_end else {}),
        }
        values = [float(item.strip()) for item in args.values.split(",")]
        result = sensitivity_sweep(plan, parameter, values, scenario, case_data, assumptions)
        name = args.parameter
    prefix = args.output_dir / plan.plan_id / "risks" / "sensitivity" / name
    paths = export_analysis_result(result, prefix)
    print(f"First failing point: {result.first_failing_point}")
    print(f"Saved: {paths[0]} and {paths[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
