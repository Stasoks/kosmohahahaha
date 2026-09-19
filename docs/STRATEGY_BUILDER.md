# Strategy Builder

Strategy Builder is a scenario-aware bounded search component that creates new
`OperatorPlan` objects from the official case inputs. It is separate from the
Strategy Advisor: Advisor modifies an existing operator plan, while Builder synthesizes
a new plan.

The Builder follows the organizer's scenario semantics:

- in `BASE`, annual total service >= 97% and annual critical service >= 99% are
  official hard constraints;
- in `MANDATORY_STRESS`, the same 97% / 99% levels are resilience benchmarks,
  not hard service constraints;
- the team may demonstrate one common strategy or justified different decisions for
  BASE and MANDATORY_STRESS;
- all other applicable hard constraints remain real constraints and are checked by the
  normal digital twin.

The Builder therefore has two explicit planning modes rather than forcing one plan to
satisfy a stronger problem than the case asks for.

## 1. Planning modes

### BASE_PLAN

Purpose: construct the standard executable supply plan.

A returned solution must be valid under the normal `BASE` simulation. This means the
existing constraint checker has already verified the official service thresholds,
capacity, storage, CAPEX, reserve, timing, Emergency-role rules and other hard
CASE_INPUT constraints.

The same plan is also simulated in MANDATORY_STRESS for diagnostics. Stress benchmark
misses are reported in `benchmark_status`; they do not invalidate an otherwise valid
BASE plan.

Typical use:

    StrategyBuilderConfig(
        planning_mode="BASE_PLAN",
        objective="MIN_COST",
    )

### STRESS_ADAPTATION

Purpose: construct a separate plan for the known mandatory stress scenario.

A returned solution must be valid under `MANDATORY_STRESS` hard constraints. The
official 97% total / 99% critical service levels are reported as resilience benchmarks.

For `MIN_COST`, the search first prefers plans that meet the benchmarks. If the
benchmarks are reachable, cost is minimized among benchmark-satisfying candidates. If
they are not reachable in the explored search space, benchmark gaps are minimized
before cost.

For `MAX_RESILIENCE`, the search directly prioritizes stress service and shortages,
then cost.

Typical use:

    StrategyBuilderConfig(
        planning_mode="STRESS_ADAPTATION",
        objective="MIN_COST",
    )

On the current official case the constructive search produces stress-valid plans that
reach both service benchmarks, but this is a result of the current input data, not a
hard-coded guarantee.

## 2. Hard constraints vs benchmarks vs operator preferences

There are three different concepts and they must not be mixed.

### Official hard constraints

These come from CASE_INPUT and are enforced by the ordinary simulator and constraint
checker. Builder does not duplicate or weaken them.

For BASE this includes the official annual service minimums:

- total service >= 0.97;
- critical service >= 0.99.

For both scenarios, applicable hard checks also include CAPEX, capacity, storage,
45-day reserve, timing, Emergency rules and scenario-specific constraints such as the
mandatory-stress loss ceiling.

### Official stress benchmarks

The BASE service thresholds are reused in stress as resilience reference levels.
Builder exposes them as:

    solution.benchmark_status["stress_total_service"]
    solution.benchmark_status["stress_critical_service"]

Each entry contains:

- benchmark;
- actual;
- gap;
- met;
- severity="benchmark";
- provenance="CASE_INPUT".

A benchmark miss is visible and quantified. It is never silently converted into a hard
organizer constraint.

### Optional operator stress targets

The UI/operator may additionally request:

- `stress_total_service_target`;
- `stress_critical_service_target`;
- `max_total_cost_mln`.

Stress service targets default to:

    stress_target_policy="SOFT"

so they are preferences used for reporting/search guidance, not organizer rules.

If an operator explicitly wants a stricter search contract, it can use:

    stress_target_policy="HARD"

This changes only the operator search requirement. It does not change CASE_INPUT and
does not relabel the target as an organizer constraint.

The maximum cost target is always treated as a hard operator search cap.

## 3. Construction

Builder does not select one of the hand-authored strategy files.

For every allowed investment combination it constructs several independent seeds:

- MIN_COST;
- MAX_RESILIENCE;
- DIVERSIFIED.

Construction is data-driven from CaseData and ModelAssumptions.

For the selected planning scenario it:

1. creates legal investment decisions;
2. creates a paid initial-stock acquisition;
3. sizes opening stock from the official 45-day reserve requirement instead of filling
   the tank arbitrarily;
4. resolves source commissioning and lead time;
5. calculates scenario demand month by month;
6. accounts for scenario delivery share and availability;
7. accounts for active storage throughput loss;
8. allocates orders within physical source capacity;
9. carries forward supply that could not yet be ordered because of lead time, so the
   opening stock consumed before the first deliveries is later recovered;
10. builds matching capacity reservations.

Stress seeds are constructed against MANDATORY_STRESS demand and delivery shares.
Therefore Lunar-ISRU underdelivery is compensated during stress-plan construction
instead of being discovered only after the fact.

The normal simulator still determines whether the result is actually feasible.

## 4. Search

After seed construction, Builder performs deterministic bounded beam search.

Candidate decisions may change:

- source/year order volume;
- source mix through transfers;
- investment timing;
- reserve policy;
- Emergency role;
- opening-stock volume.

Every candidate follows the same pipeline:

    raw TEAM_DECISION
        -> cheap structural prevalidation
        -> PlanLoader
        -> simulate(BASE)
        -> simulate(MANDATORY_STRESS)
        -> official constraint results
        -> benchmark/operator-target evaluation
        -> ranking/pruning

There is no private Builder material balance or simplified economics model.

Duplicate decisions are removed by a canonical decision key. The search is bounded by
`max_candidates`, `beam_width` and `max_iterations`. Dominance pruning is applied
only among structurally comparable candidates.

## 5. Ranking

### BASE_PLAN / MIN_COST

Priority:

1. BASE hard violations;
2. BASE shortage;
3. explicit HARD operator targets;
4. BASE cost;
5. stress resilience as tie-break information.

### BASE_PLAN / MAX_RESILIENCE

Priority:

1. BASE hard feasibility;
2. stress critical service;
3. stress total service;
4. stress shortages and reserve robustness;
5. BASE cost.

This mode searches for a more robust common strategy while never relaxing BASE
feasibility.

### STRESS_ADAPTATION / MIN_COST

Priority:

1. MANDATORY_STRESS hard feasibility;
2. explicit HARD operator targets;
3. critical-service benchmark gap;
4. total-service benchmark gap;
5. stress-scenario cost;
6. remaining resilience tie-breaks.

This ordering is intentional: a cheaper plan is not called better merely because it
saves money while missing a reachable resilience benchmark.

### STRESS_ADAPTATION / MAX_RESILIENCE

Priority:

1. MANDATORY_STRESS hard feasibility;
2. critical stress service;
3. total stress service;
4. critical/total shortage;
5. reserve/inventory robustness;
6. stress cost.

## 6. Result semantics

`StrategyBuilderResult` contains:

- status;
- full config;
- evaluated candidate count;
- iterations;
- solutions;
- search metadata;
- failure reason.

Each `StrategyBuilderSolution` contains:

- generated OperatorPlan;
- BASE SimulationResult;
- MANDATORY_STRESS SimulationResult;
- metrics for both scenarios;
- operator target status;
- official stress benchmark status;
- provenance;
- search depth;
- mutation history.

The generated plan's `scenario_id` matches the planning mode:

- BASE_PLAN -> BASE;
- STRESS_ADAPTATION -> MANDATORY_STRESS.

The result records that official inputs are CASE_INPUT, generated decisions are
TEAM_DECISION, search preferences are OPERATOR_PREFERENCE and calculated outputs are
DIGITAL_TWIN_RESULT.

## 7. Why a stress plan does not have to be BASE-valid

The case permits justified different supply, reserve, contract and investment decisions
for the standard and stress scenarios.

Therefore:

- a BASE_PLAN is accepted according to BASE hard constraints;
- a STRESS_ADAPTATION is accepted according to MANDATORY_STRESS hard constraints.

Both plans are still simulated in both scenarios so the UI can show consequences and
differences. A stress-adapted plan may overflow storage in BASE because it intentionally
orders for higher stress demand; that does not make it an invalid stress plan.

This separation is deliberate and tested.

## 8. Digital twin remains authoritative

Builder never changes:

- official demand;
- source capacity;
- prices;
- lead times;
- CAPEX limits;
- storage parameters;
- mandatory stress;
- organizer service-rule interpretation.

Every accepted solution is re-runnable through the same `PlanLoader` and
`simulate()` used for hand-authored plans.

Competition Builder rejects research sources and research-extension years.

## 9. Bounded-search limitation

Builder is a deterministic bounded heuristic search.

It returns the best strategies found in the explored search space. It does not claim:

- global optimality;
- global infeasibility;
- that failure to meet a stress benchmark proves the benchmark impossible.

If no stress adaptation reaches a benchmark, the correct output is the best found
feasible plan plus its numeric benchmark gap.

## 10. Service API

UI code should use `kosmohak.service` only.

Standard plan:

    from kosmohak.service import StrategyBuilderConfig, synthesize_strategy

    base_build = synthesize_strategy(
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
        config=StrategyBuilderConfig(
            planning_mode="BASE_PLAN",
            objective="MIN_COST",
            max_results=3,
            seed=17,
        ),
    )

Stress adaptation:

    stress_build = synthesize_strategy(
        ctx.base_scenario,
        ctx.stress_scenario,
        ctx.case_data,
        ctx.assumptions,
        config=StrategyBuilderConfig(
            planning_mode="STRESS_ADAPTATION",
            objective="MIN_COST",
            max_results=3,
            seed=17,
        ),
    )

A useful UI flow is:

    build BASE plan
        -> show official BASE hard checks
        -> run same plan in MANDATORY_STRESS
        -> show benchmark gaps and causes
        -> build STRESS_ADAPTATION
        -> compare decisions, service, shortage and cost

That workflow mirrors the case requirement instead of pretending the stress benchmark
is an additional hidden BASE constraint.
