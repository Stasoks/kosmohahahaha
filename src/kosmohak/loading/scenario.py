from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from kosmohak.domain.scenario import Scenario


class ScenarioLoader:
    FILENAMES = {"BASE": "base.yaml", "MANDATORY_STRESS": "mandatory_stress.yaml"}

    @classmethod
    def load(cls, scenario: str | Path, root_path: str | Path) -> Scenario:
        root = Path(root_path).resolve()
        candidate = Path(scenario)
        if candidate.suffix.lower() in {".yaml", ".yml"}:
            path = candidate if candidate.is_absolute() else root / candidate
        else:
            scenario_id = str(scenario).upper()
            if scenario_id not in cls.FILENAMES:
                raise ValueError(f"Unknown official scenario: {scenario}")
            path = root / "scenarios" / cls.FILENAMES[scenario_id]
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = json.loads((root / "schemas" / "scenario.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(raw)
        if raw["status"] != "CASE_INPUT":
            raise ValueError("Official scenario must be marked CASE_INPUT")
        for section_name in ("demand_multiplier", "critical_demand_multiplier"):
            for value in raw.get(section_name, {}).values():
                if float(value) < 0:
                    raise ValueError(f"Negative value in scenario section {section_name}")
        for source_values in raw.get("actual_delivery_share", {}).values():
            values = source_values.values() if isinstance(source_values, dict) else [source_values]
            if any(not 0 <= float(value) <= 1 for value in values):
                raise ValueError("Scenario actual_delivery_share must be within 0..1")
        return Scenario(
            scenario_id=str(raw["scenario_id"]),
            label_ru=str(raw.get("label_ru", raw["scenario_id"])),
            status=str(raw["status"]),
            config=raw,
            source_path=path.resolve(),
        )
