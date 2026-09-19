# Recommended BASE and quantified mitigations

This document separates the nominal minimum-cost BASE candidate from an operator
recommendation that explicitly buys a small amount of flexibility.

## Nominal benchmark

`plans/final_base.json` remains the reproducible nominal minimum-cost BASE-valid
candidate found by the declared bounded Strategy Builder search. It is useful as a
cost benchmark, but the existing sensitivity evidence shows that it is timing- and
demand-sensitive.

## Recommended BASE policy

The Streamlit Scenario Lab can run a second bounded search and select the cheapest
BASE-valid candidate that also passes three **TEAM_ASSUMPTION** guardrails:

- total demand multiplier 1.05;
- critical demand multiplier 1.05;
- Earth-Flex additional lead time +1 month.

The three checks are executed separately through the authoritative digital twin.
They are not organizer constraints and are not presented as a joint probability
model. The search remains bounded and does not claim a global optimum.

The purpose is management transparency: the operator can compare the nominal cost
floor with the explicit price of a small flexibility margin before accepting a
strategy.

## Quantified risk mitigations

Three team risks now have executable mitigation reruns:

- `R-CORE-OUTAGE`: targeted pre-booked Earth-Flex cover through the existing
  explicit plan patch;
- `R-ISRU-UNDERDELIVERY`: a pre-approved saved contingency architecture from
  `plans/resilient.json`;
- `R-LOGISTICS-DELAY`: the same pre-approved resilient architecture, which avoids
  Earth-Flex orders during the declared 2037-2039 disruption window.

A saved-plan mitigation is deliberately treated as an **ex-ante contingency plan**,
not as an instantaneous switch after the risk is observed. The backend validates the
referenced plan, re-simulates it in normal BASE and under the same risk environment,
then reports mitigation cost, residual consequence and residual impact.

The remaining risks keep qualitative mitigation descriptions unless an explicit
plan patch or saved contingency plan is provided. This avoids pretending that an
unpriced or unmodelled measure has been quantitatively demonstrated.
