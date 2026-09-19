# Stakeholder impact of the selected strategy

This document connects the existing stakeholder configuration
(`configs/stakeholders.json`) to the final reproducible calculations. It does not
invent revenue, penalties or transfers that are absent from CASE_INPUT.

## Scenario states used

- **A — BASE / FINAL BASE:** valid; minimum annual total service 100.00%;
  minimum annual critical service 100.00%; shortage 0 t; undiscounted cost
  10609.052 mln.
- **B — same FINAL BASE / MANDATORY_STRESS:** the operator decisions are unchanged;
  the plan is not stress-hard-valid; minimum annual total service 78.10%;
  minimum annual critical service 96.54%; total shortage 217.076 t; critical
  shortage 7.269 t; undiscounted cost 11111.764 mln.
- **C — STRESS ADAPTATION / MANDATORY_STRESS:** stress-hard-valid; minimum annual
  total service 97.24%; minimum annual critical service 100.00%; total shortage
  12.394 t; critical shortage 0 t; undiscounted cost 12830.504 mln.

Machine-readable source:
`results/final-evidence/master_comparison.csv`.

## Impact by stakeholder

| Stakeholder | A: standard plan | B: same decisions under stress | C: stress-specific plan | Main decision implication |
|---|---|---|---|---|
| Orbital fuel-node operator | All BASE constraints met; zero shortage; 10609.052 mln | Reserve/service degradation makes the unchanged plan unsuitable for stress | Hard-valid stress plan; 97/99 benchmarks met; higher cost | Cost minimum and resilience are different objectives; retain an explicit contingency architecture rather than calling the BASE plan universally robust |
| Critical consumers | 100% annual critical service; 0 t critical shortage | Minimum annual critical service falls to 96.54%; 7.269 t critical shortage | 100% annual critical service; 0 t critical shortage | Critical service protection is the first priority of the stress adaptation |
| Commercial consumers | 100% total service; no curtailment | Most of the 217.076 t shortage is non-critical after priority allocation | 12.394 t residual non-critical shortage; minimum annual total service 97.24% | Residual stress shortage is borne by non-critical demand after critical demand is protected |
| Fuel suppliers | BASE gross mix: A 844.737 t, B 131.526 t, C 0 t, D 360 t, E 34.904 t | Same contracted decisions, but Lunar actual delivery falls to 276 t in mandatory stress | Stress mix shifts to A 858.950 t, B 221.278 t, C 363.300 t, D 0 t, E 43.581 t | Stress planning changes the supplier portfolio materially instead of hiding Lunar underdelivery |
| Launch / logistics suppliers | Orders respect declared lead times in the accepted BASE plan | Delivery timing becomes part of resilience exposure | Stress-specific ordering must still respect the same lead times | No capacity is treated as instantaneously available; schedule changes must be made early enough |
| Financing / investor side | CAPEX 1430 mln: Lunar-ISRU 1250 + ZBO 180 | Same committed BASE investments remain sunk/committed in the replay | Stress-specific ex-ante architecture uses Earth-New + ZBO, CAPEX 540 mln, but has higher operating/procurement cost | Lower CAPEX does not imply lower lifecycle cost; scenario-specific portfolio changes who receives capital and when |

## How the balance changes

### A -> B: stress with no management adaptation

The same operator plan is replayed under the organizer's mandatory stress. Therefore
the deterioration is not caused by management changing contracts after seeing the
answer.

Consequences:

- total shortage rises by 217.076 t;
- minimum annual total service falls by 21.896 percentage points;
- minimum annual critical service falls by 3.462 percentage points;
- undiscounted cost rises by 502.713 mln because the scenario changes prices and
  physical delivery.

The operator and consumers bear the service consequence, while financing also sees
higher lifecycle cost. The unchanged supplier portfolio is unable to absorb the
mandatory Lunar underdelivery and demand increase.

### B -> C: ex-ante stress architecture

The stress-specific plan changes TEAM_DECISION while CASE_INPUT remains unchanged.

Consequences relative to B:

- shortage falls by 204.683 t;
- minimum annual total service improves by 19.132 percentage points;
- minimum annual critical service improves by 3.462 percentage points;
- undiscounted cost increases by 1718.740 mln.

This protects critical consumers completely and restores the official stress
resilience benchmarks. The trade-off is paid by the operator/financing side through a
more expensive supply portfolio.

## Example risk allocation: Earth-Core outage

The team risk `R-CORE-OUTAGE` removes Earth-Core availability for six months in
2038.

Without mitigation on FINAL BASE:

- total shortage: 17.358 t;
- critical shortage: 0 t;
- plan becomes hard-invalid because reserve and annual total-service checks fail.

The selected mitigation pre-books targeted Earth-Flex supply early enough to arrive
during the outage window.

After mitigation:

- hard violations: 0;
- total service: 100%;
- critical service: 100%;
- shortage: 0 t;
- mitigation cost relative to the normal BASE plan: **+308.609 mln**;
- residual impact score under the declared team scoring rule: 1.

This makes the allocation explicit:

- operator / financing bear the additional preparedness cost;
- Earth-Flex supplier and launch/logistics side receive additional scheduled volume;
- critical and commercial consumers avoid outage-driven shortage;
- the residual result is calculated, not described qualitatively.

Evidence:
`results/final-evidence/risks/runs/R-CORE-OUTAGE/` and
`results/final-evidence/risks/runs/R-CORE-OUTAGE/mitigation/`.

## Interpretation boundary

Stakeholder interests influence how calculated alternatives are discussed. They do not
change official service constraints, fabricate revenue or convert qualitative
preferences into money without an explicit method.

## UI presentation

The Streamlit dashboard exposes this allocation directly instead of leaving it only in
configuration files:

- **Сценарии → Кто несёт последствия стресса** shows annual BASE/STRESS/adapted
  demand, critical and commercial shortage, cost deltas and the selected-year impact.
  Commercial shortage is computed as total shortage minus critical shortage because
  critical demand is included in total demand.
- The same section states explicitly that unmet demand is not monetised without an
  input value for lost service and that mandatory-stress Lunar-ISRU underdelivery does
  not create an automatic refund.
- **Сценарии → Интересы, обязательства и распределение риска** exposes interests/KPI,
  obligations, cost bearers, risk bearers and calculated A/B/C outcomes for every
  stakeholder.
- **Риски и чувствительность → Реестр рисков** shows the stakeholders affected by the
  selected team risk before the risk, in the risk state and, when a quantitative
  mitigation exists, after mitigation.
- **Риски и чувствительность → Участники** repeats the full responsibility map so the
  jury does not need to infer cost/risk allocation from configuration JSON.

These UI statements remain descriptive consequences of the digital-twin calculation.
They do not introduce revenue, mission-loss valuation, penalties or compensation
terms absent from CASE_INPUT.
