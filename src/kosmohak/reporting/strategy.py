from __future__ import annotations

import csv
import json
from pathlib import Path


def export_plan_comparison(comparison: dict, output_dir: str | Path) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    serializable = {
        key: value for key, value in comparison.items() if key != "results"
    }
    (directory / "strategy_comparison.json").write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rows = serializable["plans"]
    fields = list(rows[0]) if rows else []
    with (directory / "strategy_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        if fields:
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list))
                        else value
                        for key, value in row.items()
                    }
                )
    return directory
