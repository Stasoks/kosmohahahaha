from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_team_risks_config_contains_required_register_fields() -> None:
    path = ROOT / "configs" / "risks" / "team_risks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "risk_id",
        "name",
        "description",
        "event",
        "cause",
        "period_start",
        "period_end",
        "affected_parameters",
        "factor_changes",
        "dependencies",
        "owner",
        "likelihood",
        "likelihood_status",
        "source_references",
        "combination_policy",
        "anticipated_consequence",
        "mitigation",
        "residual_consequence",
        "stakeholder_ids",
        "metadata",
    }

    assert payload["status"] == "TEAM_ASSUMPTION"
    assert payload["risks"]
    for risk in payload["risks"]:
        assert required <= set(risk)


def test_stakeholders_config_exists_and_has_participants() -> None:
    path = ROOT / "configs" / "stakeholders.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "TEAM_ASSUMPTION"
    assert payload["participants"]
    for participant in payload["participants"]:
        assert {
            "stakeholder_id",
            "name",
            "interests",
            "kpis",
            "obligations",
            "cost_bearer",
            "risk_bearer",
            "relevant_risks",
        } <= set(participant)


def test_source_x_scalability_fixture_preserves_official_rows() -> None:
    official_path = ROOT / "data" / "supply_sources.csv"
    extended_path = ROOT / "data" / "supply_sources_with_X.csv"

    with official_path.open(encoding="utf-8", newline="") as stream:
        official = list(csv.DictReader(stream))
    with extended_path.open(encoding="utf-8", newline="") as stream:
        extended = list(csv.DictReader(stream))

    official_by_id = {row["source_id"]: row for row in official}
    extended_by_id = {row["source_id"]: row for row in extended}

    for source_id, row in official_by_id.items():
        assert extended_by_id[source_id] == row

    assert extended_by_id["X"]["name"] == "Source-X"
    assert extended_by_id["X"]["status"] == "TEAM_ASSUMPTION"
