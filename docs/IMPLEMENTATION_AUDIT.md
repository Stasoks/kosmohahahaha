# Implementation audit before starter-kit migration

Audit date: 2026-09-18. Official source: `SpaceEconomyPolicy/test_oil`, commit `cec6de1950276091689e71a67f9a875fb4ca6213`. Old implementation: `/home/stas/python_projects/kosmohack` before this migration (34 tests passing).

Precedence used throughout the migration:

1. official machine-readable CSV/YAML/schema/validation data;
2. official README and calculation documentation;
3. old implementation;
4. previous team assumptions.

| Requirement | Official source | Old implementation | Status | Action |
|---|---|---|---|---|
| Case inputs | `data/*.csv` | Duplicated in `data/case_data.json` | Incompatible | Remove the JSON dataset and load official CSV files directly. |
| Data validation | `schemas/demand.schema.json`, `schemas/supply_sources.schema.json`, semantic rules | Hand-written validation of the old JSON shape | Partial | Validate official rows against schemas and enforce cross-row invariants in `CaseDataLoader`. |
| Source identifiers | `supply_sources.csv`: `A`–`E`, stable names for scenario joins | Internal IDs `earth_core`, `earth_flex`, etc. | Incompatible | Use official source IDs natively; resolve YAML overrides by official source name. |
| Scenario loading | `scenarios/base.yaml`, `scenarios/mandatory_stress.yaml` | Python scenario classes containing configuration values | Incompatible | Replace with YAML-backed `ScenarioLoader` and declarative accessors. |
| BASE reliability | `base.yaml`, `CALCULATION_RULES.md` | Reliability stored but not applied | Compatible | Reuse behavior; retain reliability as metadata only. |
| Stress ISRU delivery | `mandatory_stress.yaml` | Applied 55/75/100 without reliability | Compatible semantics, wrong source | Read shares and years from YAML. |
| Plan contract | `schemas/plan.schema.json` | Custom `name/channels/investments` document | Incompatible | Implement the official `plan_id/scenario_id/decisions` envelope with documented participant fields. |
| Fixed plan across scenarios | `STRESS_PROTOCOL.md` | Same object could be simulated twice | Compatible | Keep decisions immutable; CLI scenario override changes environment only. |
| Monthly timeline | User migration requirement; official timestep is implementation-defined | 72-month deterministic loop | Compatible | Reuse timeline and monthly state pattern. |
| Reserved / ordered / delivered / served separation | README §10 | Separate in most calculations, but old naming was channel-specific | Mostly compatible | Make all four explicit using official source IDs in monthly and annual output. |
| Lead-time source units | `supply_sources.csv` | Emergency was stored in duplicated JSON with precomputed two months | Incompatible provenance | Preserve official six-week value; convert through a named TEAM_ASSUMPTION policy. |
| Earth-New timing | CSV range and investment commissioning rule | 24-month commissioning delay plus assumed zero operational lag | Compatible only as an assumption | Select 24 months in TEAM_ASSUMPTION, derive commissioning from exercise, document zero post-commission lag because no second lag is defined. |
| Lunar-ISRU timing | CSV range 1–2 months after commissioning | Selected two months | Compatible only as an assumption | Load range, select two months in TEAM_ASSUMPTION and enforce funding/availability. |
| Material balance | `CALCULATION_RULES.md`, V01 | Explicit monthly identity | Compatible | Reuse and rename fields to official terms. |
| No negative inventory | `CALCULATION_RULES.md`, V02 | Shortage separated from zero-bounded inventory | Compatible | Reuse. |
| Critical demand nesting | `demand.csv`, V09 | Correctly used `total - critical` | Compatible | Reuse with official demand rows. |
| Throughput losses | `storage_options.csv`, V06 | Applied once to gross inflow; overflow edge handled after loss | Compatible | Reuse pure calculation and verify against V06. |
| Storage overflow | `CALCULATION_RULES.md` §13 | Physical acceptance capped and violation emitted | Compatible, violation shape incomplete | Reuse physics and emit official-style structured violation. |
| Holding cost | `CALCULATION_RULES.md` §8 | Monthly trapezoid average | Valid TEAM_ASSUMPTION | Keep and document. |
| Take-or-pay | `CALCULATION_RULES.md`, V03–V04 | `max(order, TOP × reserved)` once per year | Compatible | Reuse pure economics and official tests. |
| Reservation proration | `CALCULATION_RULES.md`, V05 | Annual charge prorated by active months | Compatible | Reuse and verify against V05. |
| Investment data | `investment_options.csv`, `storage_options.csv` | Values read from duplicated JSON | Incompatible provenance | Load official rows and ensure Earth-New 360 and ZBO 180 are not double-counted. |
| CAPEX constraints | `constraints.csv` | Limits read from old JSON | Incompatible source | Drive checks from constraint definitions. |
| Reserve | `constraints.csv`, V07 | 45/365 physical check plus Emergency equivalence | Compatible arithmetic, wrong source | Load 45-day limit; keep explicit equivalence proof and TEAM_ASSUMPTION timing conversion. |
| Emergency streak | `constraints.csv` | Checked plan role for >2 consecutive years | Compatible | Use official constraint ID and threshold. |
| Service checks | `constraints.csv` | BASE hard; stress custom benchmark | Mostly compatible | Load BASE thresholds from CSV; reuse them as clearly labeled non-hard resilience benchmarks in stress. |
| Violation structure | Migration specification | `code/severity/scenario/period/channel/actual/limit/units/message` | Incomplete | Add `constraint_id`, `operator`, `excess_or_gap`, `reason`, and official `source_id`. |
| Official V01–V10 | `validation/control_cases.md`, `expected_checks.json` | Equivalent unit tests existed, but not data-driven from official expectations | Incompatible test contract | Add a single official suite loading expected values from the organizer JSON. |
| Export contract | `schemas/export.schema.json` | Custom summary JSON plus CSV files | Incompatible | Add and validate official result envelope; retain detailed participant CSV exports. |
| Comparison | Migration specification | Aggregate summary comparison | Partial | Add annual service/inventory and per-source delivery comparisons. |
| Provenance | `CASE_RULES.md` | Old `organizer_input/operator_decision/model_assumption/scenario_override` vocabulary | Incompatible terminology | Use only `CASE_INPUT`, `TEAM_DECISION`, `TEAM_ASSUMPTION`. |
| CLI | Migration specification | Useful skeleton with old scenario names and loaders | Partial | Reuse argument flow; switch defaults to official root and uppercase scenario IDs. |
| Optimizer and stochastic modules | Official README / migration exclusions | Absent | Compatible | Keep absent. |

## Upstream integrity observation

The official validator at commit `cec6de1` passes syntax, data, scenario, schema, and V01–V10 inventory checks, then stops on one upstream documentation link: `data/README.md` references missing `docs/ERRATA_AND_PROVENANCE.md`. The migration preserves organizer files unchanged and does not silently repair that link. The starter validator's `check_no_ready_solution` is intentionally not applicable after participant `src/`, `tests/`, `configs/`, and `results/` are added.

## Migration decision

Reusable calculation ideas are retained, but the public data model is rebuilt around official CSV/YAML/schema contracts. Backward compatibility with the old JSON dataset and old plan shape is intentionally not provided.

## Strategy-evaluator audit (2026-09-18)

The second implementation stage kept all official inputs and V01–V10 unchanged and
corrected two participant-layer weaknesses:

1. `inventory_policy.initial_inventory` created physical stock from a scalar and used
   simplified costing. It is now rejected when positive. Opening stock is produced by a
   traceable pre-horizon source contract and passes lead-time, availability, capacity,
   TOP, reservation, loss and storage checks.
2. Monthly export exposed `delivered_for_balance_t`, whose bookkeeping definition used
   an artificial `+ losses - losses` identity. Public flow now follows only
   `gross -> losses -> net -> accepted -> available -> served -> closing`.

The deterministic core was then wrapped in a data-driven environment/risk layer. The
layer reruns the same immutable plan, derives consequences from `SimulationResult`, and
adds scoring, matrix/register, explicit mitigation reruns, sensitivity and reverse
stress without optimizer, random failures, Monte Carlo or inferred probabilities.

No conflict with official starter semantics was found. The preparatory-acquisition rule
is a stricter participant decision contract inside the official schema's intentionally
extensible `decisions` object; no official CSV, YAML, schema or validation vector was
changed.
