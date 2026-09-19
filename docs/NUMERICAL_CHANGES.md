# Intentional numerical and fingerprint changes

## Partial-year price override

- Old behavior: one arithmetic mean of twelve monthly prices multiplied by annual
  payable volume, regardless of order timing.
- New behavior: every ordered tonne is charged at its order-month price. TOP-only
  volume is charged at the time-weighted price over active contractual months.
- Reason: non-uniform monthly orders must not receive an unrelated calendar average.
- Affected outputs: procurement, take-or-pay effect, displayed effective variable
  price, total/discounted cost for partial-period price shocks.

Official BASE and MANDATORY_STRESS example totals are unchanged because their relevant
annual contract prices are uniform within each affected year.

## Run ID

- Old behavior: fingerprint included text from official input files only.
- New behavior: fingerprint includes deterministic serialization of effective
  `CaseData`, including research sources, future years, applicable constraints, and
  provenance configuration.
- Affected output: run IDs intentionally change; physical/economic results do not.

## New KPI

`cost_per_served_ton_mln` and its discounted variant are added. They are `null` when
served demand is zero.
