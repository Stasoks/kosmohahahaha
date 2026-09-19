# UI integration API

The backend is framework-neutral. Streamlit, FastAPI, or another frontend should load
inputs once and call the public functions; the UI must not reimplement physics.

```python
from kosmohak import (
    add_research_source,
    extend_horizon,
    evaluate_plan,
    evaluate_both_scenarios,
    repair_plan,
    improve_plan,
    improve_resilience,
    compare_plans,
)

pair = evaluate_both_scenarios(
    plan, base_scenario, stress_scenario, case_data, assumptions
)
st.json(pair["BASE"].summary)
st.dataframe(pair["BASE"].annual)
st.dataframe([violation.to_dict() for violation in pair["BASE"].violations])
```

For an advisor screen, show the original plan and `suggestion.patch.to_dict()` side by
side. Applying the patch is a separate user action. Do not replace the original plan
when the suggestion is merely viewed.

All functions return Python dataclasses/dictionaries suitable for JSON/CSV conversion.
Existing export helpers write stable result, comparison, risk, and advisor artifacts.
No UI code is changed by this backend branch.
