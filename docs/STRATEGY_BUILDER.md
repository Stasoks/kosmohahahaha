# Strategy Builder

Strategy Builder is a separate bounded search workflow for creating new OperatorPlan strategies from the official case inputs. It does not replace or change the existing Strategy Advisor.

## Builder vs Advisor

- Strategy Advisor starts from an existing OperatorPlan and proposes local repairs/improvements while preserving the operator's intent.
- Strategy Builder starts from CaseData, ModelAssumptions, BASE, MANDATORY_STRESS, and operator search targets. It constructs new plans and searches combinations of TEAM_DECISION variables.

Both rely on the same normal PlanLoader validation and the same simulate() digital twin. The Builder has no private material-balance, cost, storage, lead-time, reserve, or mandatory-stress model.

## Inputs and provenance

Official case values and constraints remain CASE_INPUT and are immutable during search. Generated plan decisions are TEAM_DECISION. Optional search targets such as stress service or a maximum cost are operator preferences, not organizer requirements. Simulation outputs remain DIGITAL_TWIN_RESULT.

Competition mode rejects research sources and research-extension years. It operates on the official competition horizon and official sources only.

## Search

The current implementation uses deterministic bounded beam search:

1. Construct several data-driven seeds from official investments and source metadata.
2. Validate each candidate with the normal plan loader.
3. Simulate BASE and MANDATORY_STRESS with the normal digital twin.
4. Rank and prune candidates.
5. Generate additional decisions from the current beam, including source/year order changes, transfers between sources, investment timing changes, reserve-policy changes, and Emergency-role changes.
6. Repeat until the iteration or candidate budget is exhausted.

Duplicate decision sets are removed by a canonical decision key. The search also uses bounded candidate budgets, beam pruning, result-cache metadata, and structural/dominance pruning.

The same inputs, config, and seed produce the same result ordering.

## Objectives

### MIN_COST

Among BASE-valid plans satisfying all configured operator targets, prefer lower undiscounted digital-twin cost. Resilience metrics are deterministic tie-breaks.

### MAX_RESILIENCE

Among BASE-valid plans, prioritize minimum annual critical stress service, minimum annual total stress service, stress shortages, reserve/inventory robustness, and then cost.

No arbitrary weighted score is used.

## Operator targets

StrategyBuilderConfig supports stress_total_service_target, stress_critical_service_target, max_total_cost_mln, search budgets, and a deterministic seed.

Stress service targets are checked against the minimum annual MANDATORY_STRESS service level, not only the aggregate whole-horizon service level. Targets are not silently promoted to official constraints.

## Result semantics

StrategyBuilderResult reports the search status, config, evaluated-candidate count, iterations, search metadata, solutions, and an explicit failure reason when needed.

Each StrategyBuilderSolution contains the generated plan, BASE result, MANDATORY_STRESS result, objective metrics, target-satisfaction details, provenance, search depth, and mutation history.

Possible failure statuses describe only the explored bounded search space. In particular, the Builder never claims global infeasibility.

## Global-optimum limitation

Strategy Builder is a deterministic bounded heuristic search. Returned plans are the best strategies found in the explored search space. They are not a proof of global optimality, and failure to find a target-satisfying plan is not a proof that no such plan exists globally.

## Python API

Internal package usage:

    from kosmohak.builder import StrategyBuilderConfig, build_strategies

    result = build_strategies(
        base_scenario=base_scenario,
        stress_scenario=stress_scenario,
        case_data=case_data,
        assumptions=assumptions,
        config=StrategyBuilderConfig(
            objective="MIN_COST",
            stress_total_service_target=0.97,
            stress_critical_service_target=0.99,
            max_candidates=3000,
            beam_width=20,
            max_iterations=8,
            max_results=3,
            seed=17,
        ),
    )

Normal UI code should use the stable kosmohak.service.synthesize_strategy() facade instead of importing Builder internals.
