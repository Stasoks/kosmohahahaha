import csv
import json

from jsonschema import Draft202012Validator

from kosmohak.reporting.export import build_comparison, export_comparison, export_result
from kosmohak.simulation import simulate


def test_same_inputs_produce_identical_results(plan, stress_scenario, case_data, assumptions):
    first = simulate(plan, stress_scenario, case_data, assumptions).to_dict()
    second = simulate(plan, stress_scenario, case_data, assumptions).to_dict()
    assert first == second


def test_export_matches_official_schema_and_csv_lengths(tmp_path, base_result, case_data):
    directory = export_result(base_result, tmp_path / "BASE", case_data.root)
    envelope = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    schema = json.loads((case_data.root / "schemas/export.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(envelope)
    assert len(list(csv.DictReader((directory / "monthly.csv").open(encoding="utf-8")))) == 72
    assert {path.name for path in directory.iterdir()} == {
        "result.json", "summary.json", "violations.json", "monthly.csv", "annual.csv", "channels.csv", "costs.csv"
    }


def test_base_stress_comparison_uses_same_plan_and_has_annual_sources(tmp_path, base_result, stress_result):
    comparison = build_comparison(base_result, stress_result)
    assert comparison["plan_id"] == base_result.summary["plan_id"] == stress_result.summary["plan_id"]
    assert len(comparison["annual"]) == 6
    assert len(comparison["source_deliveries"]) == 30
    export_comparison(base_result, stress_result, tmp_path)
    assert (tmp_path / "comparison.json").is_file()
    assert (tmp_path / "comparison.csv").is_file()

