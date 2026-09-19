"""Contract tests for the ``kosmohak.service`` facade used by the dashboard.

They pin the *shape* of the public API (what the UI relies on) and the mapping
of failures to structured :class:`ServiceError` objects.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from kosmohak import service as contract

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.kernel


@pytest.fixture(scope="module")
def context():
    return contract.load_application_context(ROOT)


def test_context_loads_official_inputs(context):
    assert context.case_data is not None
    assert context.risks, "risk register must be loaded from configs"
    assert context.optional_config_errors == ()


def test_validate_plan_accepts_official_raw(plan, case_data, assumptions):
    outcome = contract.validate_plan(plan.raw, case_data, assumptions)
    assert outcome.valid is True
    assert outcome.plan is not None
    assert outcome.errors == []


def test_validate_plan_rejects_malformed_raw(case_data, assumptions):
    outcome = contract.validate_plan({}, case_data, assumptions)
    assert outcome.valid is False
    assert outcome.plan is None
    assert outcome.errors
    assert outcome.errors[0].code == "PLAN_VALIDATION_ERROR"


def test_evaluate_plan_returns_valid_base_result(plan, base_scenario, case_data, assumptions):
    result = contract.evaluate_plan(plan, base_scenario, case_data, assumptions)
    assert result.summary["valid"] is True
    assert result.summary["scenario_id"] == "BASE"
    assert result.summary["plan_id"] == plan.plan_id
    assert result.monthly and result.annual and result.sources and result.costs


def test_evaluate_both_scenarios_returns_both_conditions(
    plan, base_scenario, stress_scenario, case_data, assumptions
):
    pair = contract.evaluate_both_scenarios(
        plan, base_scenario, stress_scenario, case_data, assumptions
    )
    assert {"BASE", "MANDATORY_STRESS"} <= set(pair)
    assert pair["BASE"].summary["scenario_id"] == "BASE"
    assert pair["MANDATORY_STRESS"].summary["scenario_id"] == "MANDATORY_STRESS"


def test_compare_plans_never_declares_a_winner(plan, base_scenario, stress_scenario, case_data, assumptions):
    comparison = contract.compare_plans(
        [plan], base_scenario, stress_scenario, case_data, assumptions
    )
    assert comparison["status"] == "DIGITAL_TWIN_RESULT"
    assert comparison["winner_selected"] is False
    assert len(comparison["plans"]) == 1


def test_official_demand_sensitivity_covers_three_levels(plan, base_scenario, case_data, assumptions):
    sensitivity = contract.run_official_demand_sensitivity(plan, base_scenario, case_data, assumptions)
    assert [point["value"] for point in sensitivity.points] == ["LOW", "BASE", "HIGH"]
    if sensitivity.first_failing_point is not None:
        assert sensitivity.first_failing_point["value"] in {"LOW", "BASE", "HIGH"}


def test_risk_portfolio_contract(context, plan, base_scenario, case_data, assumptions):
    portfolio = contract.evaluate_risks(plan, base_scenario, context.risks, case_data, assumptions)
    assert portfolio.evaluations
    assert portfolio.risk_register
    assert portfolio.risk_matrix
    assert isinstance(portfolio.unknown_likelihood_risks, list)


def test_to_service_error_maps_exceptions():
    assert contract.to_service_error(ValueError("bad")).code == "VALUE_ERROR"
    assert contract.to_service_error(FileNotFoundError("gone")).code == "FILE_NOT_FOUND"


def test_result_summary_is_a_defensive_copy(base_result):
    summary = contract.result_summary(base_result)
    assert summary["plan_id"] == base_result.summary["plan_id"]
    summary["plan_id"] = "mutated"
    assert contract.result_summary(base_result)["plan_id"] == base_result.summary["plan_id"]


def test_violations_table_shape(base_result):
    table = contract.violations_table(base_result)
    assert isinstance(table, list)
    for row in table:
        assert "code" in row and "severity" in row


def test_export_plan_results_writes_files(base_result, tmp_path):
    output = contract.export_plan_results(base_result, tmp_path / "export", ROOT)
    output_path = Path(output)
    assert output_path.exists()
    files = [path for path in output_path.rglob("*") if path.is_file()] if output_path.is_dir() else [output_path]
    assert files


def test_build_download_bundle_is_a_zip(plan, case_data, base_result, stress_result, tmp_path):
    bundle_path = tmp_path / "bundle.zip"
    result = contract.build_download_bundle(
        plan=plan,
        case_data=case_data,
        base_result=base_result,
        stress_result=stress_result,
        output_path=bundle_path,
    )
    path = Path(result)
    assert path.exists()
    assert path.suffix == ".zip"
    assert zipfile.is_zipfile(path)


def test_build_plan_and_load_plan_round_trip(plan, case_data, assumptions, tmp_path):
    target = tmp_path / "plan.json"
    contract.save_plan(plan, target)
    assert target.exists()
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    outcome = contract.validate_plan(reloaded, case_data, assumptions)
    assert outcome.valid is True
