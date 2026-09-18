from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from kosmohak.domain.result import SimulationResult


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _cell(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _cell(row.get(field)) for field in fields})


def export_result(result: SimulationResult, output_dir: str | Path, case_root: str | Path) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    envelope = result.to_export_envelope()
    schema = json.loads((Path(case_root) / "schemas" / "export.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(envelope)
    _write_json(directory / "result.json", envelope)
    _write_json(directory / "summary.json", result.summary)
    _write_json(directory / "violations.json", [item.to_dict() for item in result.violations])
    _write_csv(directory / "monthly.csv", result.monthly)
    _write_csv(directory / "annual.csv", result.annual)
    _write_csv(directory / "channels.csv", result.sources)
    _write_csv(directory / "costs.csv", result.costs)
    return directory


def build_comparison(base: SimulationResult, stress: SimulationResult) -> dict[str, Any]:
    summary_metrics = [
        "undiscounted_cost_mln",
        "discounted_cost_mln",
        "total_service_level",
        "critical_service_level",
        "total_shortage_t",
        "critical_shortage_t",
        "total_losses_t",
        "emergency_usage_t",
        "final_inventory_t",
        "violation_count",
        "hard_violation_count",
    ]
    summary = {
        key: {
            "BASE": base.summary[key],
            "MANDATORY_STRESS": stress.summary[key],
            "difference": stress.summary[key] - base.summary[key],
        }
        for key in summary_metrics
    }
    annual = []
    for base_row, stress_row in zip(base.annual, stress.annual):
        annual.append(
            {
                "year": base_row["year"],
                "base_total_service": base_row["total_service_level"],
                "stress_total_service": stress_row["total_service_level"],
                "base_critical_service": base_row["critical_service_level"],
                "stress_critical_service": stress_row["critical_service_level"],
                "base_shortage_t": base_row["shortage_t"],
                "stress_shortage_t": stress_row["shortage_t"],
                "base_closing_inventory_t": base_row["closing_inventory_t"],
                "stress_closing_inventory_t": stress_row["closing_inventory_t"],
                "base_losses_t": base_row["losses_t"],
                "stress_losses_t": stress_row["losses_t"],
            }
        )
    source_deliveries = []
    stress_index = {(row["source_id"], row["year"]): row for row in stress.sources}
    for row in base.sources:
        other = stress_index[(row["source_id"], row["year"])]
        source_deliveries.append(
            {
                "source_id": row["source_id"],
                "year": row["year"],
                "base_actual_delivered_t": row["actual_delivered_t"],
                "stress_actual_delivered_t": other["actual_delivered_t"],
                "difference_t": other["actual_delivered_t"] - row["actual_delivered_t"],
            }
        )
    return {
        "plan_id": base.summary["plan_id"],
        "scenarios": ["BASE", "MANDATORY_STRESS"],
        "summary": summary,
        "annual": annual,
        "source_deliveries": source_deliveries,
        "violations": {
            "BASE": [item.to_dict() for item in base.violations],
            "MANDATORY_STRESS": [item.to_dict() for item in stress.violations],
        },
    }


def export_comparison(base: SimulationResult, stress: SimulationResult, output_dir: str | Path) -> dict[str, Any]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    comparison = build_comparison(base, stress)
    _write_json(directory / "comparison.json", comparison)
    rows = [
        {"scope": "summary", "id": key, **values}
        for key, values in comparison["summary"].items()
    ]
    rows.extend(
        {
            "scope": "annual",
            "id": row["year"],
            "BASE": json.dumps({key: value for key, value in row.items() if key.startswith("base_")}),
            "MANDATORY_STRESS": json.dumps({key: value for key, value in row.items() if key.startswith("stress_")}),
            "difference": "",
        }
        for row in comparison["annual"]
    )
    _write_csv(directory / "comparison.csv", rows)
    return comparison

