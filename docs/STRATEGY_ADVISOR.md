# Strategy Advisor

The advisor is a client of the digital twin. It proposes immutable `OperatorPlan`
patches and accepts a candidate only after a full `simulate()` run. It has no material
balance, contract-cost, or feasibility model of its own.

## Modes

- `REPAIR`: remove BASE hard violations, then rank lexicographically by changed
  decisions, structural/investment changes, normalized magnitude, and cost delta.
- `IMPROVE`: keep BASE valid and return only non-increasing-cost candidates inside the
  change budget.
- `RESILIENCE`: keep BASE valid and return candidates whose selected mandatory-stress
  shortage metrics are not worse.
- `EXPLORE`: secondary mode that classifies distinct simulated source mixes into
  comparison archetypes; it does not select a winner.

```python
from kosmohak.optimization import DecisionLocks, OptimizerConfig, repair_plan

answer = repair_plan(
    plan, base_scenario, stress_scenario, case_data, assumptions,
    locks=DecisionLocks(
        investments={"ZBO": True},
        sources={"D": True},
        emergency_role=True,
    ),
    config=OptimizerConfig(seed=17, max_candidates=200),
)
```

Each `SuggestedPlan` contains the typed path-level patch, resulting plan, distance
components, BASE and stress before/after results, cost/service/shortage deltas, and
violations removed or introduced. Locks are checked before simulation. Structurally
invalid candidates are cheaply rejected, but final acceptance always uses the full
digital twin.

The current deterministic search is bounded local enumeration, not a global optimum
proof. `no_feasible_repair_found` means no candidate in the saved search space passed;
it never means that a fabricated feasible solution was substituted.

Use `save_optimization_result()` to persist optimizer config, result, suggested plans,
and patches. `reopen_suggested_plan()` reconstructs a saved suggestion for a repeated
simulation.
