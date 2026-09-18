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
from kosmohak.risk import find_failure_threshold


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find a deterministic one-factor failure threshold")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--parameter", required=True)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument("--stop", required=True, type=float)
    parser.add_argument("--step", required=True, type=float)
    parser.add_argument("--target-constraint", default="ANY_HARD")
    parser.add_argument("--source-id")
    parser.add_argument("--storage-id")
    parser.add_argument("--investment-id")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
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
    parameter = {
        "name": args.parameter,
        **({"source_id": args.source_id} if args.source_id else {}),
        **({"storage_id": args.storage_id} if args.storage_id else {}),
        **({"investment_id": args.investment_id} if args.investment_id else {}),
        **({"period_start": args.period_start} if args.period_start else {}),
        **({"period_end": args.period_end} if args.period_end else {}),
    }
    result = find_failure_threshold(
        plan,
        parameter,
        {"start": args.start, "stop": args.stop, "step": args.step},
        args.target_constraint,
        scenario,
        case_data,
        assumptions,
    )
    prefix = args.output_dir / plan.plan_id / "risks" / "reverse_stress" / args.parameter
    paths = export_analysis_result(result, prefix)
    print(f"Last safe: {result.last_safe_value}; first failing: {result.first_failing_value}")
    print(f"Saved: {paths[0]} and {paths[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
