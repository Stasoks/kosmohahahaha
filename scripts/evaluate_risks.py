#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kosmohak.loading import AssumptionsLoader, CaseDataLoader, PlanLoader, RiskLoader, ScenarioLoader
from kosmohak.reporting import export_risk_portfolio
from kosmohak.risk import evaluate_risk_set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic TEAM risks for one immutable plan")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--risks", required=True, type=Path)
    parser.add_argument("--scenario", default="BASE", choices=("BASE", "MANDATORY_STRESS"))
    parser.add_argument("--case-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--assumptions", type=Path, default=PROJECT_ROOT / "configs/model_assumptions.json")
    parser.add_argument("--scoring", type=Path, default=PROJECT_ROOT / "configs/risk_scoring.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case_data = CaseDataLoader.load(args.case_root)
    assumptions = AssumptionsLoader.load(args.assumptions)
    plan = PlanLoader.load(args.plan, case_data, assumptions)
    scenario = ScenarioLoader.load(args.scenario, args.case_root)
    risks = RiskLoader.load(args.risks)
    portfolio = evaluate_risk_set(
        plan,
        scenario,
        risks,
        case_data,
        assumptions,
        args.scoring,
    )
    directory = args.output_dir / plan.plan_id / "risks"
    export_risk_portfolio(portfolio, directory, args.case_root)
    print(f"Evaluated {len(risks)} risks for {plan.plan_id} on {scenario.scenario_id}")
    print(f"Unknown likelihood: {', '.join(portfolio.unknown_likelihood_risks) or 'none'}")
    print(f"Saved: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
