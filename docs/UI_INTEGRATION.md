# UI backend API v1

`kosmohak.service` is the stable, in-process boundary for Streamlit or another Python
frontend. It does not start an HTTP server. The simulation remains the only source of
truth for physics, economics, and constraints.

```python
from kosmohak.service import UI_BACKEND_API_VERSION

assert UI_BACKEND_API_VERSION == "1.0"
```

The UI should not import `simulation`, `risk`, `optimization`, `workspace`,
`reporting`, or `loading` directly for normal user flows.

## Startup

Load the application once and keep the returned typed context in Streamlit session
state or another application-level container.

```python
from pathlib import Path
from kosmohak.service import load_application_context

ROOT = Path(__file__).resolve().parent
ctx = load_application_context(ROOT)

case_data = ctx.case_data
assumptions = ctx.assumptions
base_scenario = ctx.base_scenario
stress_scenario = ctx.stress_scenario
```

The official case, assumptions, BASE, and MANDATORY_STRESS inputs are required and
raise their real loader error if invalid. The team risk portfolio and stakeholder
file are optional. Missing or invalid optional files produce empty/`None` values and
an explicit `ctx.optional_config_errors` entry.

## Plans

Load a JSON file:

```python
from kosmohak.service import load_plan

plan = load_plan(
    ROOT / "configs/operator_plan_example.json",
    ctx.case_data,
    ctx.assumptions,
)
```

Build from a form dictionary:

```python
from kosmohak.service import build_plan

plan = build_plan(raw_form_plan, ctx.case_data, ctx.assumptions)
```

Both functions use the same official JSON Schema, `OperatorPlan.from_dict()`, and
domain validation path. `build_plan()` deep-copies the input and does not mutate the
form dictionary.

For a non-throwing form-validation flow:

```python
from kosmohak.service import validate_plan

validation = validate_plan(raw_form_plan, ctx.case_data, ctx.assumptions)
if not validation.valid:
    for error in validation.errors:
        st.error(f"{error.field or 'plan'}: {error.message}")
else:
    plan = validation.plan
```

Save and reopen without changing semantic content:

```python
from kosmohak.service import load_plan, save_plan

path = save_plan(plan, ROOT / "workspaces/current-plan.json")
plan = load_plan(path, ctx.case_data, ctx.assumptions)
```

## BASE and MANDATORY_STRESS

```python
from kosmohak.service import evaluate_both_scenarios

pair = evaluate_both_scenarios(
    plan,
    ctx.base_scenario,
    ctx.stress_scenario,
    ctx.case_data,
    ctx.assumptions,
)
base_result = pair["BASE"]
stress_result = pair["MANDATORY_STRESS"]
comparison = pair["comparison"]

st.json(base_result.summary)
st.dataframe(base_result.annual)
```

`evaluate_plan()` is available when the UI needs one environment.
`compare_plans()` evaluates several strategies and does not select a winner.

Small read-only view helpers are available when convenient:

```python
from kosmohak.service import comparison_table, result_summary, violations_table

st.json(result_summary(base_result))
st.dataframe(violations_table(base_result))
st.dataframe(comparison_table(comparison))
```

The result's own `summary`, `annual`, `monthly`, `sources`, and `costs` fields remain
the primary data for tables and charts.

## Risks

```python
from kosmohak.service import evaluate_risks, evaluate_single_risk

portfolio = evaluate_risks(
    plan,
    ctx.base_scenario,
    ctx.risks,
    ctx.case_data,
    ctx.assumptions,
)
one_risk = evaluate_single_risk(
    plan,
    ctx.base_scenario,
    ctx.risks[0],
    ctx.case_data,
    ctx.assumptions,
)
```

For a risk that has an explicit mitigation plan patch, use
`evaluate_risk_mitigation(...)`. No mitigation benefit is invented by the service
layer.

## Sensitivity and reverse stress

```python
from kosmohak.service import (
    run_official_demand_sensitivity,
    run_reverse_stress,
    run_sensitivity,
)

sensitivity = run_sensitivity(
    plan,
    "demand_multiplier",
    [0.9, 1.0, 1.1],
    ctx.base_scenario,
    ctx.case_data,
    ctx.assumptions,
)
official_range = run_official_demand_sensitivity(
    plan, ctx.base_scenario, ctx.case_data, ctx.assumptions
)
threshold = run_reverse_stress(
    plan,
    "demand_multiplier",
    {"start": 1.0, "stop": 1.5, "step": 0.05},
    "ANY_HARD",
    ctx.base_scenario,
    ctx.case_data,
    ctx.assumptions,
)
```

## Strategy advisor

Advisor calls return typed suggestions with the original and suggested BASE/STRESS
results, a patch, changed decisions, distance, and cost/service/shortage deltas.

```python
from kosmohak.service import OptimizerConfig, repair_strategy

repair = repair_strategy(
    plan,
    ctx.base_scenario,
    ctx.stress_scenario,
    ctx.case_data,
    ctx.assumptions,
    config=OptimizerConfig(seed=17, max_candidates=200),
)
```

Viewing a suggestion does not modify the original plan. Applying it is a separate,
explicit action:

```python
from kosmohak.service import apply_strategy_suggestion

if repair.suggestions and user_confirmed:
    approved_plan = apply_strategy_suggestion(
        plan,
        repair.suggestions[0],
        new_plan_id="operator-approved-repair-01",
    )
```

The other modes are `improve_strategy()`, `improve_strategy_resilience()`, and
`explore_strategy_alternatives()`. All accept the same plan/scenario/case/assumption
arguments and optional `locks=` and `config=` keyword arguments.

## Research source and future horizon

The UI passes ordinary dictionaries through factories and works with one persistent
workspace. The factories only construct typed specs; validation requiring the
official case and existing overlay happens when the source/year is added.

```python
import json
from kosmohak.service import (
    add_workspace_source,
    build_effective_case,
    build_future_year_spec,
    build_research_source_spec,
    create_workspace,
    extend_workspace_horizon,
)

raw_workspace = json.loads(
    (ROOT / "configs/research_workspace_example.json").read_text(encoding="utf-8")
)

workspace = create_workspace(ctx.case_data)
source_f = build_research_source_spec(raw_workspace["sources"][0])
workspace = add_workspace_source(workspace, source_f)

year_2041 = build_future_year_spec(raw_workspace["future_years"][0])
workspace = extend_workspace_horizon(workspace, year_2041)
effective_case = build_effective_case(workspace)

assert "F" in effective_case.sources
assert 2041 in effective_case.demand
```

The backend never extrapolates demand, prices, capacity, availability, reliability,
or constraints. Every future year must explicitly cover every effective source.

Save and reopen the same overlay:

```python
from kosmohak.service import load_case_workspace, save_case_workspace

workspace_path = save_case_workspace(
    workspace, ROOT / "workspaces/current-workspace.json"
)
workspace = load_case_workspace(workspace_path, ctx.case_data)
effective_case = build_effective_case(workspace)
```

## Exports and downloadable ZIP

Individual facade exports are `export_plan_results()`,
`export_scenario_comparison()`, `export_risk_results()`, and
`export_advisor_results()`. For one UI download use:

```python
from kosmohak.service import build_download_bundle

zip_path = build_download_bundle(
    plan=plan,
    case_data=ctx.case_data,
    base_result=pair["BASE"],
    stress_result=pair["MANDATORY_STRESS"],
    comparison=pair["comparison"],
    risks=portfolio,
    advisor_result=repair,
    output_path=ROOT / "downloads" / f"{plan.plan_id}.zip",
)

st.download_button(
    "Download calculation bundle",
    data=zip_path.read_bytes(),
    file_name=zip_path.name,
    mime="application/zip",
)
```

The ZIP contains the plan, complete BASE/STRESS exports, comparison JSON/CSV,
optional risk/workspace/advisor artifacts, and `manifest.json`. The export timestamp
is created after simulation and never participates in a simulation run ID.

## UI-friendly errors

Service functions keep raising real validation exceptions. Convert an exception only
at the UI boundary:

```python
from kosmohak.service import to_service_error

try:
    plan = build_plan(raw_form_plan, ctx.case_data, ctx.assumptions)
except Exception as exc:
    error = to_service_error(exc)
    st.error(f"[{error.code}] {error.field or 'input'}: {error.message}")
```

`to_service_error()` explicitly recognizes plan validation, risk validation, case
data, JSON, missing-file, and general value errors. It does not suppress or log away
the original exception.

## Stability contract

Stable for `UI_BACKEND_API_VERSION == "1.0"`:

- names and documented signatures in `kosmohak.service`;
- `ApplicationContext`, `ServiceError`, and `ValidationResult` fields;
- `evaluate_both_scenarios()` keys `BASE`, `MANDATORY_STRESS`, and `comparison`;
- explicit advisor preview/apply behavior;
- download bundle paths and manifest fields documented above.

Internal implementation details:

- module layout and helper functions below `simulation`, `risk`, `optimization`,
  `workspace`, `reporting`, and `loading`;
- advisor candidate-generation/search internals;
- internal serialization mechanics used to produce the stable exported artifacts.
