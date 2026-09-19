from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from kosmohak.loading import PlanLoader, RiskLoader
from kosmohak.reporting import export_result
from kosmohak.risk import evaluate_risk, sensitivity_sweep
from kosmohak.simulation import simulate
from kosmohak.workspace import (
    CaseWorkspace,
    FutureYearSpec,
    ResearchSourceSpec,
    load_workspace,
    save_workspace,
)


ROOT = Path(__file__).resolve().parents[2]


def _source_f():
    return ResearchSourceSpec(
        source_id="F",
        name="Research-Orbital-Tug",
        capacity_t_per_year=24,
        variable_cost_mln_per_t=4.25,
        reservation_rate_mln_per_t_year_capacity=0.2,
        take_or_pay_share=0.5,
        lead_time_min_value=4,
        lead_time_max_value=4,
        lead_time_unit="month",
        availability_rule={"type": "calendar", "available_from": "2040-07"},
        reliability_metadata={"semantics": "metadata_only", "basis": "research fixture"},
        notes="Independent source unlike official A-E.",
        provenance={"basis": "acceptance fixture", "source": "TEST:EXT-01"},
    )


def _future_2041(source_ids):
    return FutureYearSpec(
        year=2041,
        base_total_demand_t=12,
        base_critical_demand_t=8,
        low_total_t=10,
        high_total_t=15,
        source_price_assumptions={source_id: 5.0 for source_id in source_ids},
        source_capacity_assumptions={source_id: 24.0 for source_id in source_ids},
        source_availability_assumptions={source_id: 1.0 for source_id in source_ids},
        reliability_assumptions={source_id: "metadata_only" for source_id in source_ids},
        applicable_constraints=("BASE_CRITICAL_SERVICE", "BASE_TOTAL_SERVICE"),
        notes="Explicit research extension; no organizer forecast implied.",
        provenance={"basis": "acceptance fixture", "source": "TEST:HOR-01"},
    )


def _extended(case_data):
    workspace = CaseWorkspace.from_official(case_data)
    returned = workspace.add_source(_source_f())
    assert returned is workspace
    workspace.extend_horizon(_future_2041((*case_data.sources, "F")))
    return workspace, workspace.build()


def _extended_plan(tmp_path, effective, assumptions, *, order=12, reservation=24):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    raw["plan_id"] = "extension-f-2041"
    raw["decisions"]["supply_orders"].append(
        {"source_id": "F", "mode": "monthly", "values": {"2040-12": order}}
    )
    raw["decisions"]["capacity_reservations"].extend(
        [
            {"source_id": "F", "year": 2040, "reserved_capacity_t": reservation},
            {"source_id": "F", "year": 2041, "reserved_capacity_t": 0},
        ]
    )
    raw["decisions"]["inventory_policy"]["reserve_strategy_by_year"]["2041"] = "physical"
    raw["decisions"]["emergency_role_by_year"]["2041"] = "reserve_only"
    path = tmp_path / "extended-plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return PlanLoader.load(path, effective, assumptions), raw


def test_add_source_and_extend_horizon_do_not_mutate_official(case_data):
    before = copy.deepcopy(case_data)
    workspace, effective = _extended(case_data)
    assert case_data == before
    assert "F" not in case_data.sources
    assert effective.sources["F"].status == "TEAM_ASSUMPTION"
    assert effective.sources["F"].provenance["scope"] == "RESEARCH_EXTENSION"
    assert effective.demand[2041].status == "TEAM_ASSUMPTION"
    assert effective.horizon_provenance[2041]["scope"] == "RESEARCH_EXTENSION"
    assert workspace.to_dict()["status"] == "TEAM_ASSUMPTION"


def test_source_f_crosses_official_horizon_and_exports(
    tmp_path, case_data, assumptions, base_scenario
):
    _, effective = _extended(case_data)
    plan, _ = _extended_plan(tmp_path, effective, assumptions)
    result = simulate(plan, base_scenario, effective, assumptions)
    assert len(result.monthly) == 84
    april = next(row for row in result.monthly if row["month"] == "2041-04")
    assert april["gross_delivery_by_source"]["F"] == pytest.approx(12)
    assert any(row["source_id"] == "F" and row["year"] == 2041 for row in result.sources)
    assert result.summary["research_extension_years"] == [2041]
    assert result.summary["research_source_ids"] == ["F"]
    directory = export_result(result, tmp_path / "export", case_data.root)
    envelope = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert envelope["effective_case_provenance"]["horizon"]["2041"]["scope"] == "RESEARCH_EXTENSION"


def test_source_f_capacity_preserves_request_and_plan(
    tmp_path, case_data, assumptions, base_scenario
):
    _, effective = _extended(case_data)
    plan, raw = _extended_plan(tmp_path, effective, assumptions, order=30, reservation=30)
    before = json.dumps(plan.raw, sort_keys=True)
    result = simulate(plan, base_scenario, effective, assumptions)
    row = next(item for item in result.sources if item["source_id"] == "F" and item["year"] == 2040)
    assert row["requested_order_t"] == 30
    assert row["feasible_order_t"] == pytest.approx(12)
    assert any(item.code == "CAPACITY_EXCEEDED" and item.source_id == "F" for item in result.violations)
    assert json.dumps(plan.raw, sort_keys=True) == before == json.dumps(raw, sort_keys=True)


def test_research_risk_and_sensitivity_target_f_in_2041(
    tmp_path, case_data, assumptions, base_scenario
):
    _, effective = _extended(case_data)
    plan, _ = _extended_plan(tmp_path, effective, assumptions)
    risk = RiskLoader.from_dict(
        {
            "risk_id": "F-OUT-2041",
            "name": "F outage",
            "event": "F unavailable in April",
            "cause": "fixture",
            "period_start": "2041-04",
            "period_end": "2041-04",
            "factor_changes": [{"factor": "availability_share", "source_id": "F", "value": 0}],
            "owner": "test",
            "likelihood": {"likelihood_type": "unknown"},
            "metadata": {"status": "TEAM_ASSUMPTION"},
        }
    )
    evaluation = evaluate_risk(plan, base_scenario, risk, effective, assumptions)
    april = next(row for row in evaluation.risk_result.monthly if row["month"] == "2041-04")
    assert april["gross_delivery_by_source"].get("F", 0) == 0
    sweep = sensitivity_sweep(
        plan,
        {"name": "delivery_share", "source_id": "F", "period_start": "2041-04", "period_end": "2041-04"},
        [1.0, 0.0],
        base_scenario,
        effective,
        assumptions,
    )
    assert len(sweep.points) == 2


def test_effective_case_changes_run_id(tmp_path, plan, case_data, assumptions, base_scenario):
    official = simulate(plan, base_scenario, case_data, assumptions)
    _, effective = _extended(case_data)
    extended_plan, _ = _extended_plan(tmp_path, effective, assumptions)
    first = simulate(extended_plan, base_scenario, effective, assumptions)
    second = simulate(extended_plan, base_scenario, effective, assumptions)
    assert first.summary["run_id"] == second.summary["run_id"]
    assert first.summary["run_id"] != official.summary["run_id"]


def test_future_year_requires_explicit_assumptions(case_data):
    workspace = CaseWorkspace.from_official(case_data)
    with pytest.raises(ValueError, match="source_price_assumptions"):
        workspace.extend_horizon(
            FutureYearSpec(
                year=2041,
                base_total_demand_t=10,
                base_critical_demand_t=5,
                low_total_t=8,
                high_total_t=12,
                source_price_assumptions={},
                source_capacity_assumptions={source_id: 1 for source_id in case_data.sources},
                source_availability_assumptions={source_id: 1 for source_id in case_data.sources},
                reliability_assumptions={source_id: "unknown" for source_id in case_data.sources},
                applicable_constraints=(),
                notes="invalid fixture",
                provenance={"basis": "test", "source": "TEST"},
            )
        )


def test_workspace_save_reopen_and_second_future_year(
    tmp_path, case_data, assumptions, base_scenario
):
    workspace, effective = _extended(case_data)
    source_ids = tuple(effective.sources)
    workspace.extend_horizon(
        FutureYearSpec(
            year=2042,
            base_total_demand_t=14,
            base_critical_demand_t=9,
            low_total_t=11,
            high_total_t=17,
            source_price_assumptions={source_id: 5.2 for source_id in source_ids},
            source_capacity_assumptions={source_id: 24 for source_id in source_ids},
            source_availability_assumptions={source_id: 1 for source_id in source_ids},
            reliability_assumptions={source_id: "metadata_only" for source_id in source_ids},
            applicable_constraints=("BASE_TOTAL_SERVICE", "BASE_CRITICAL_SERVICE"),
            notes="Second explicit future year.",
            provenance={"basis": "acceptance fixture", "source": "TEST:HOR-2042"},
        )
    )
    path = save_workspace(workspace, tmp_path / "workspace.json")
    reopened = load_workspace(path, case_data)
    first_case, second_case = workspace.build(), reopened.build()
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    raw["plan_id"] = "extension-f-2042"
    raw["decisions"]["supply_orders"].append(
        {"source_id": "F", "mode": "monthly", "values": {"2040-12": 12}}
    )
    raw["decisions"]["capacity_reservations"].extend(
        [
            {"source_id": "F", "year": 2040, "reserved_capacity_t": 24},
            {"source_id": "F", "year": 2041, "reserved_capacity_t": 0},
            {"source_id": "F", "year": 2042, "reserved_capacity_t": 0},
        ]
    )
    raw["decisions"]["inventory_policy"]["reserve_strategy_by_year"]["2041"] = "physical"
    raw["decisions"]["inventory_policy"]["reserve_strategy_by_year"]["2042"] = "physical"
    raw["decisions"]["emergency_role_by_year"]["2041"] = "reserve_only"
    raw["decisions"]["emergency_role_by_year"]["2042"] = "reserve_only"
    plan_path = tmp_path / "plan-2042.json"
    plan_path.write_text(json.dumps(raw), encoding="utf-8")
    plan_2042 = PlanLoader.load(plan_path, second_case, assumptions)
    result = simulate(plan_2042, base_scenario, second_case, assumptions)
    assert len(result.monthly) == 96
    assert first_case == second_case
