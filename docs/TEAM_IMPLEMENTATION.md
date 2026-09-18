# Participant calculation engine

This document describes the participant implementation layered on the official `test_oil` starter repository. Organizer files in `data/`, `scenarios/`, `schemas/`, `validation/`, and the original documentation remain authoritative and are not rewritten to fit the code. The pre-migration comparison is recorded in [`IMPLEMENTATION_AUDIT.md`](IMPLEMENTATION_AUDIT.md).

## Architecture

The public contract is:

```python
result = simulate(plan, scenario, case_data, assumptions)
```

The data flow is deliberately one-way:

```text
official CSV -> CaseDataLoader -> CaseData (CASE_INPUT)
official YAML -> ScenarioLoader -> Scenario (CASE_INPUT)
official plan envelope -> PlanLoader -> OperatorPlan (TEAM_DECISION)
team assumptions JSON -> AssumptionsLoader (TEAM_ASSUMPTION)
                          |
                          v
                  monthly digital twin
                          |
                          v
              SimulationResult + violations + export
```

`CaseDataLoader` validates official demand/source rows with the supplied JSON schemas and additionally checks semantic invariants: unique IDs/names, critical demand nested in total demand, non-negative capacities and costs, take-or-pay and loss shares in `0..1`, valid lead-time ranges, investment composition, and constraint operators.

`ScenarioLoader` validates and applies `scenarios/base.yaml` or `scenarios/mandatory_stress.yaml`. No scenario year, multiplier, source name, or delivery share is duplicated in Python.

## Plan format and provenance

[`configs/operator_plan_example.json`](../configs/operator_plan_example.json) uses the official envelope from `schemas/plan.schema.json`:

```text
plan_id
scenario_id
decisions
  supply_orders[]
  capacity_reservations[]
  investments[]
  inventory_policy
  emergency_role_by_year
metadata.status = TEAM_DECISION
```

The official schema intentionally permits participant-defined fields inside decision objects. This implementation documents those fields through the example plan and validates them semantically. Orders support `monthly` and `annual_even`; the latter means twelve equal monthly order placements, not immediate annual delivery.

`scenario_id` is the saved/default context. An explicit CLI scenario overrides only the environment for the run. It never changes the plan decisions, so `both` compares the same immutable plan under BASE and MANDATORY_STRESS.

## Monthly simulation

The official 2035–2040 demand rows create 72 model months. Annual demand is allocated according to the selected TEAM_ASSUMPTION (`uniform` in the example). The monthly event sequence is:

1. apply investment/commissioning state;
2. select active storage;
3. receive eligible shipments whose lead time has elapsed;
4. apply the scenario `actual_delivery_share` once;
5. calculate throughput losses once;
6. enforce storage capacity and record unaccepted overflow;
7. serve nested critical demand first and remaining demand second;
8. keep physical inventory non-negative and record shortage separately;
9. calculate holding and fixed OPEX;
10. retain orders, reservations, pipeline, deliveries, state, costs, and violations.

The control material balance is preserved:

```text
I_end = I_start + Q_delivered_for_balance - Losses - Q_served
```

`gross_throughput_t` is the actual inflow before losses. Losses are always `gross_throughput_t * active_loss_rate`. On overflow, `delivered_for_balance_t` is the accepted net volume plus losses already incurred before the capacity check; unaccepted post-loss fuel remains `overflow_t` and never enters inventory. This keeps both the official loss base and the material identity explicit.

The model preserves separate fields for reserved capacity, ordered volume, eligible order, planned arrival, actual delivery, accepted volume, served demand, and inventory. Orders above an active contractual/physical limit or before source commissioning remain visible, create structured violations, and have a rejected physical portion. They are not silently converted into supply.

## Lead time and investments

- A / Earth-Core: official 12-month delivery lead.
- B / Earth-Flex: official 4-month delivery lead.
- C / Earth-New: option exercise starts the selected official-range project lead; capacity commissions afterward.
- D / Lunar-ISRU: available after timely funding and 2038 commissioning; orders then use the selected official-range delivery lead.
- E / Emergency: the official value remains six weeks in CSV and is converted by the documented TEAM_ASSUMPTION.

ZBO changes capacity, throughput loss rate, and fixed OPEX from its commissioning month. Earth-New charges the 90 option fee and 270 exercise cost exactly once; 360 is not charged again. Lunar-ISRU funding charges 1250 once. ZBO CAPEX is read from the investment row and is not duplicated from the equivalent storage row.

## Economics

Annual contract economics uses the official rules:

```text
reserved_period = annual_reserved_capacity * active_fraction
payable_volume = max(ordered_volume, TOP_share * reserved_period)
variable_payment = active_variable_price * payable_volume
reservation_payment = reservation_rate * annual_reserved_capacity * active_fraction
```

Reservation is a separate cost component. TOP is included inside procurement and reported as an informational effect, not added a second time. Holding cost uses monthly stock-time. Total cost is procurement + reservation + holding + fixed OPEX + CAPEX. Initial stock is paid in the first model year without creating a duplicate arrival.

Discounting uses one disclosed real rate and an end-of-calendar-year convention. The organizer does not provide revenue, profit, ROI, or mission-failure damage, so they are absent.

## Constraints and diagnostics

CSV-backed checks use their official `constraint_id`, operator, value, unit, scenario scope, and severity. Structural checks derived from official calculation rules cover source capacity, contractual order volume, source availability, and storage capacity.

Every violation contains:

```text
code, constraint_id, severity, scenario, period, source_id,
actual, operator, limit, unit, excess_or_gap, reason, human_message
```

BASE service constraints are hard. In MANDATORY_STRESS the same service thresholds are shown as explicit resilience benchmarks, while the YAML/CSV loss ceiling and all `ALL` constraints remain hard. `valid` depends only on hard violations.

The physical 45-day reserve is checked at the start of each year using the scenario's total demand and the official `45/365` conversion. An Emergency contract is accepted as equivalent only when capacity, `reserve_only` role, and the non-emergency bridge through the converted lead time are demonstrated.

## BASE and MANDATORY_STRESS

BASE applies no reliability multiplier. Reliability strings remain visible metadata for a future, separately specified risk block.

MANDATORY_STRESS reads all values from YAML: demand multipliers, source-specific variable-price multipliers, Lunar-ISRU delivery shares, affected years, and loss ceiling. The ISRU share is the final scenario share and is not multiplied by reliability again. Reservation tariffs, CAPEX, and other unaffected costs remain unchanged.

## Verification

The suite in `tests/official/test_v01_v10.py` loads expected outputs directly from `validation/expected_checks.json` and reproduces every official control vector:

- V01 material balance;
- V02 shortage without negative inventory;
- V03–V04 TOP and no duplicate payment;
- V05 reservation proration;
- V06 throughput loss once;
- V07 45-day reserve;
- V08 structured capacity violation and excess;
- V09 nested critical demand;
- V10 scenario delivery without a reliability double multiplier.

Additional unit/integration tests cover official loading, schemas, lead time, pipeline lifecycle, ZBO, Earth-New, ISRU, priority, capacity, CAPEX, Emergency role, invalid input, reproducibility, BASE/STRESS integration, official export validation, and comparison consistency.

## Install and run

```bash
python3 -m pip install '.[dev]'
python3 -m pytest
```

```bash
python3 scripts/evaluate_plan.py --plan configs/operator_plan_example.json --scenario BASE
python3 scripts/evaluate_plan.py --plan configs/operator_plan_example.json --scenario MANDATORY_STRESS
python3 scripts/evaluate_plan.py --plan configs/operator_plan_example.json --scenario both
```

Optional flags are `--case-root`, `--assumptions`, and `--output-dir`.

## Exports

Each run creates:

```text
results/<plan_id>/<scenario_id>/
  result.json       # validates against schemas/export.schema.json
  summary.json
  violations.json
  monthly.csv
  annual.csv
  channels.csv
  costs.csv
```

`both` also creates `comparison.json` and `comparison.csv`. Comparison includes total and discounted costs, annual total/critical service, shortage, inventory, losses, per-source physical deliveries, Emergency usage, and violations.

## Active TEAM_ASSUMPTION values

All are stored with value, unit, and basis in [`configs/model_assumptions.json`](../configs/model_assumptions.json):

1. Earth-New project lead: 24 months within the official 18–24 range.
2. Earth-New post-commission operational delivery lag: zero; the official lead is interpreted as preparation/commissioning and no second lag is specified.
3. Lunar-ISRU delivery lead after commissioning: 2 months within the official 1–2 range.
4. Demonstration real discount rate: 5% per year; it requires final team justification.
5. Discount convention: end of each calendar year, base year 2035.
6. Monthly annual-demand allocation: uniform.
7. Monthly average inventory: trapezoid of opening and closing inventory.
8. Week-to-model-month conversion: seven days/week, `365/12` days/model month, rounded upward; Emergency therefore takes two model months.

The official 365-day denominator in the 45-day reserve formula is CASE_INPUT semantics, not a team assumption.

## Baseline limitations

This is one-node, one-commodity, deterministic monthly aggregation. It does not model propellant chemistry, tanks, vehicles, trajectories, orbital mechanics, revenue, mission-failure damages, probabilistic reliability, sensitivity automation, optimizer, MILP, Optuna, RL, Monte Carlo, custom risk scenarios, recommendation logic, automatic plan repair, database, or UI. The empty `risk_register` in the official export envelope is intentional at this stage.
