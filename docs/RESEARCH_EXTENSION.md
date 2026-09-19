# Research extension

`CaseWorkspace` creates an effective case without mutating the official `CaseData`.
Generic transport mechanics consume source availability rules, so a new source does
not require a new branch in the simulator.

```python
from kosmohak.workspace import CaseWorkspace, ResearchSourceSpec, FutureYearSpec

workspace = CaseWorkspace.from_official(case_data)
workspace.add_source(ResearchSourceSpec(
    source_id="F",
    name="Research-Orbital-Tug",
    capacity_t_per_year=24,
    variable_cost_mln_per_t=4.25,
    reservation_rate_mln_per_t_year_capacity=0.20,
    take_or_pay_share=0.50,
    lead_time_min_value=4,
    lead_time_max_value=4,
    lead_time_unit="month",
    availability_rule={"type": "calendar", "available_from": "2040-07"},
    reliability_metadata={"semantics": "metadata_only"},
    notes="Research source, not organizer data.",
    provenance={"basis": "team research", "source": "TEAM:source-F"},
))

source_ids = ("A", "B", "C", "D", "E", "F")
workspace.extend_horizon(FutureYearSpec(
    year=2041,
    base_total_demand_t=410,
    base_critical_demand_t=260,
    low_total_t=328,
    high_total_t=512.5,
    source_price_assumptions={source_id: {"value": 8, "basis": "team"} for source_id in source_ids},
    source_capacity_assumptions={source_id: 100 for source_id in source_ids},
    source_availability_assumptions={source_id: 1 for source_id in source_ids},
    reliability_assumptions={source_id: "metadata_only" for source_id in source_ids},
    applicable_constraints=("BASE_TOTAL_SERVICE", "BASE_CRITICAL_SERVICE", "RESERVE_45D"),
    notes="Explicit research year; no official extrapolation is claimed.",
    provenance={"basis": "explicit team forecast", "source": "TEAM:forecast-2041"},
))

effective_case = workspace.build()
result = simulate(plan, scenario, effective_case, assumptions)
assert len(result.monthly) == 84
```

Every future year must be contiguous and explicitly cover every effective source for
price, capacity, availability, and reliability metadata. Applicable constraints are
an explicit list. The API does not extrapolate organizer demand, prices, scenarios,
or constraints.

Availability rules are `calendar`, `investment`, or `always`. Official Earth-New and
Lunar-ISRU investment relationships are annotated while loading the official case;
the generic shipment pipeline only sees the rule.

Workspace serialization is supported by `save_workspace()` and `load_workspace()`.
The serialized overlay preserves provenance and rebuilds the same effective case and
run ID.
