#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p results/operator_acceptance
LOG="results/operator_acceptance/run.log"
: > "$LOG"

run_plan () {
  local n="$1"
  local file="$2"
  echo "===== TEST $n: $file =====" | tee -a "$LOG"
  python3 scripts/evaluate_plan.py     --plan "operator_tests/plans/$file"     --scenario both     --output-dir "results/operator_acceptance/$n" 2>&1 | tee -a "$LOG"
  echo | tee -a "$LOG"
}

run_risk () {
  local n="$1"
  local riskfile="$2"
  echo "===== TEST $n: $riskfile =====" | tee -a "$LOG"
  python3 scripts/evaluate_risks.py     --plan "operator_tests/plans/01_balanced_isru.json"     --risks "operator_tests/risks/$riskfile"     --scenario BASE     --output-dir "results/operator_acceptance/$n" 2>&1 | tee -a "$LOG"
  echo | tee -a "$LOG"
}

run_plan 01 01_balanced_isru.json
run_plan 02 02_earth_new_strategy.json
run_plan 03 03_full_diversification.json
run_plan 04 04_earth_core_heavy.json
run_plan 05 05_no_zbo_stress.json
run_plan 06 06_emergency_abuse.json
run_plan 07 07_initial_stock_core_top.json
run_plan 08 08_impossible_initial_isru.json
run_risk 09 09_core_outage_2038.json
run_risk 10 10_core_price_shock_2038.json

echo "Done. See results/operator_acceptance/ and $LOG"
