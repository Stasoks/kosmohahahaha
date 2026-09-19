from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from kosmohak.domain.risk import RiskPortfolioResult
from kosmohak.reporting.export import export_result


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def export_risk_portfolio(
    portfolio: RiskPortfolioResult,
    output_dir: str | Path,
    case_root: str | Path,
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    _json(root / "risk_register.json", portfolio.risk_register)
    _csv(root / "risk_register.csv", portfolio.risk_register)
    _json(root / "risk_matrix.json", portfolio.risk_matrix)
    _json(root / "risk_portfolio.json", portfolio.to_dict())
    _json(root / "risk_scoring.json", portfolio.scoring_config)
    matrix_rows: list[dict[str, Any]] = []
    for likelihood, columns in portfolio.risk_matrix["cells"].items():
        for impact, risks in columns.items():
            matrix_rows.append(
                {
                    "likelihood_score": int(likelihood),
                    "impact_score": int(impact),
                    "risks": risks,
                }
            )
    for item in portfolio.risk_matrix["unknown_likelihood"]:
        matrix_rows.append(
            {
                "likelihood_score": "UNKNOWN",
                "impact_score": item["impact_score"],
                "risks": [item],
            }
        )
    _csv(root / "risk_matrix.csv", matrix_rows)
    runs = root / "runs"
    for evaluation in portfolio.evaluations:
        export_result(evaluation.risk_result, runs / evaluation.risk.risk_id, case_root)
        if evaluation.mitigation:
            export_result(
                evaluation.mitigation.risk_result,
                runs / evaluation.risk.risk_id / "mitigation",
                case_root,
            )
    return root


def export_analysis_result(result: Any, output_prefix: str | Path) -> tuple[Path, Path]:
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    _json(json_path, payload)
    _csv(csv_path, payload.get("points", payload.get("evaluated_points", [])))
    return json_path, csv_path
