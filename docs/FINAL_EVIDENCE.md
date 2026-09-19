# Final competition evidence pack

This document is a map of the reproducible case outputs used for the final
management note, UI and presentation. The calculation source of truth is the normal
digital twin; this file contains no independently calculated numbers.

## Reproduce

```bash
python scripts/generate_final_evidence.py
```

The command rebuilds the selected BASE plan and the mandatory-stress adaptation with
deterministic Builder settings, re-runs the normal simulator, official demand
sensitivity, reverse stress and the team risk portfolio, and writes the outputs under
`results/final-evidence/`.

## Selected plans

- `plans/final_base.json` — generated `BASE_PLAN / MIN_COST` candidate. It is
  valid under every applicable BASE hard constraint.
- `plans/final_stress_adaptation.json` — generated
  `STRESS_ADAPTATION / MIN_COST` plan. It is valid under every applicable
  MANDATORY_STRESS hard constraint. The 97% total / 99% critical service levels are
  reported as stress resilience benchmarks, not relabelled as hard constraints.

The Builder is bounded heuristic search. These are the selected reproducible plans
found in the declared search space, not claims of global optimality.

## Three-way comparison

| Case | Plan / environment | Hard-valid | Minimum annual total service | Minimum annual critical service | Shortage, t | Undiscounted cost, mln |
|---|---|---:|---:|---:|---:|---:|
| A | FINAL BASE / BASE | yes | 100.00% | 100.00% | 0.000 | 10609.052 |
| B | exact same FINAL BASE / MANDATORY_STRESS | no | 78.10% | 96.54% | 217.076 | 11111.764 |
| C | FINAL STRESS ADAPTATION / MANDATORY_STRESS | yes | 97.24% | 100.00% | 12.394 | 12830.504 |

The stress replay B changes only the environment. It therefore isolates the
consequence of the mandatory stress on the standard plan. Case C then changes the
TEAM_DECISION while keeping the mandatory-stress CASE_INPUT unchanged, exposing the
effect and cost of adaptation.

### Stress effect: B - A

- undiscounted cost: +502.713 mln;
- shortage: +217.076 t;
- minimum annual total service: -21.896 percentage points;
- minimum annual critical service: -3.462 percentage points.

### Adaptation effect: C - B

- undiscounted cost: +1718.740 mln;
- shortage: -204.683 t;
- minimum annual total service: +19.132 percentage points;
- minimum annual critical service: +3.462 percentage points.

The adapted stress plan still leaves 12.394 t of non-critical shortage in 2040, while
meeting the 97% total and 99% critical resilience benchmarks in every stress year. No
stress demand, source capacity, CAPEX limit or other CASE_INPUT is increased to hide
the gap.

Machine-readable source: `results/final-evidence/master_comparison.csv`,
`master_comparison.json`, `master_deltas.json` and
`decision_comparison.json`.

## Decision difference

The selected BASE plan enables Lunar-ISRU and ZBO, does not exercise Earth-New and
uses a predominantly Earth-Core + Lunar supply structure.

The selected stress adaptation enables Earth-New and ZBO, disables Lunar-ISRU and
uses more Earth-Flex/Earth-New supply. This is a scenario-specific planning decision:
the mandatory stress explicitly reduces Lunar-ISRU actual delivery in 2038–2039.

Exact orders, reservations, investment dates, reserve policy and Emergency roles are
stored in the two plan JSON files and in
`results/final-evidence/decision_comparison.json`.

## Comparison with common-strategy alternatives

`results/final-evidence/alternatives/` re-evaluates the three existing distinct
common strategies and FINAL BASE on the same BASE / MANDATORY_STRESS inputs.

Relative to FINAL BASE:

- `cost-focused` costs 7.85% more in BASE, but improves aggregate stress service by
  4.02 percentage points and reduces stress shortage by 61.703 t;
- `diversified` costs 11.23% more, improves aggregate stress service by 6.60
  percentage points and reduces shortage by 101.223 t;
- `resilient` costs 11.42% more, improves aggregate stress service by 7.11
  percentage points and reduces shortage by 109.127 t.

None of these comparisons turns the plan name into a verdict. They expose the
cost-versus-fixed-plan-resilience trade-off required for management choice. The
stress-specific adaptation remains a separate scenario plan and reaches the official
stress service benchmarks more closely than the common BASE plans.

## Official demand sensitivity

`results/final-evidence/sensitivity/official_low_base_high.*` uses the organizer LOW,
BASE and HIGH demand values without replacing the selected plan.

- LOW: service is 100%, but the fixed BASE plan becomes infeasible because reduced
  demand causes storage overflow. This is a flexibility limitation, not a service
  shortage.
- BASE: valid, 100% total and critical service.
- HIGH: the fixed BASE plan becomes infeasible; aggregate total service is 83.68% and
  shortage is 273.084 t.

The point of this test is not to claim that the selected BASE orders should remain
unchanged after demand information changes. It quantifies how brittle that fixed
decision set is and motivates adaptive replanning.

## Reverse stress

`results/final-evidence/reverse_stress/demand_multiplier.*` varies a deterministic
demand multiplier while keeping the strategy unchanged.

- last tested safe multiplier: 1.01;
- first tested failing multiplier: 1.02;
- first reported target failure: annual BASE total-service constraint in 2040
  (95.50% vs 97%).

This is a grid threshold, not a continuous mathematical proof.

## Additional sensitivity

Two additional one-factor checks are exported under
`results/final-evidence/sensitivity/`.

**Earth-Flex lead-time delay.** The fixed FINAL BASE plan is already infeasible at a
+1 month delay: annual total service in 2040 falls to 96.35%, total shortage is
14.244 t and the 45-day reserve is also breached. The reverse-stress grid therefore
reports 0 months as the last safe tested delay and +1 month as the first failing
point.

**ZBO loss multiplier.** The plan remains valid at the official loss value
(multiplier 1.0), but at 1.25x the modeled ZBO throughput loss the 2040 opening
reserve falls to 43.83 days. Service is still 100% at that point, so the test exposes
a reserve-margin failure before a service failure.

Together with LOW/HIGH demand these results identify demand, flexible-channel timing
and storage loss as material sensitivities of the selected low-cost BASE architecture.

## Team risks and mitigation

The complete portfolio is exported to `results/final-evidence/risks/`.

For `R-CORE-OUTAGE`, the mitigation was updated for the selected final BASE plan:
Earth-Flex cover is pre-booked to arrive during the six-month Earth-Core outage
window. Recalculation through the unchanged digital twin gives:

- mitigated risk run hard-valid: yes;
- total service: 100%;
- critical service: 100%;
- shortage: 0 t;
- mitigation cost relative to the normal BASE plan: +308.609 mln;
- residual impact score under the team scoring rule: 1.

The risk scenario, mitigation decisions and residual result remain separate objects;
no probability is invented where the case provides no statistical basis.

## Other evidence

- official arithmetic/control vectors: `tests/official/`;
- implementation and provenance: `docs/TEAM_IMPLEMENTATION.md`;
- calculation rules: `docs/CALCULATION_RULES.md`;
- stress methodology: `docs/STRESS_PROTOCOL.md`;
- scientific evidence map: `docs/SCIENTIFIC_BASIS.md`;
- future-period/source extension: `docs/RESEARCH_EXTENSION.md`;
- UI backend contract: `docs/UI_INTEGRATION.md`;
- final budget and decision gates: `docs/FINAL_ROADMAP.md`;
- stakeholder consequences and trade-offs: `docs/STAKEHOLDER_IMPACT.md`.

## Important interpretation

The FINAL BASE plan is the minimum-cost BASE-valid Builder result under the declared
bounded search. The official LOW/HIGH and reverse-stress results show that it is not a
universally robust fixed plan. The management note must therefore present cost versus
flexibility explicitly rather than calling the cheapest plan unconditionally best.
