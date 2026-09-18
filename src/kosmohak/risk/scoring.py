from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RiskScoringError(ValueError):
    pass


def load_scoring_config(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("status") != "TEAM_ASSUMPTION":
        raise RiskScoringError("Risk scoring config must be marked TEAM_ASSUMPTION")
    if raw.get("impact_aggregation") != "maximum_dimension_score":
        raise RiskScoringError("Only maximum_dimension_score impact aggregation is supported")
    required = {
        "critical_service_degradation_pp",
        "shortage_share",
        "incremental_cost_pct",
        "hard_violation_count",
        "disruption_duration_months",
    }
    missing = required - set(raw.get("impact_dimensions", {}))
    if missing:
        raise RiskScoringError(f"Missing impact scoring dimensions: {sorted(missing)}")
    for name, levels in raw["impact_dimensions"].items():
        scores = [int(item["score"]) for item in levels]
        minimums = [float(item["min_inclusive"]) for item in levels]
        if scores != [1, 2, 3, 4, 5] or minimums != sorted(minimums):
            raise RiskScoringError(f"Dimension {name} must define ordered scores 1..5")
    return raw


def _ordinal_score(value: float, levels: list[dict[str, Any]]) -> int:
    score = 1
    for level in levels:
        if value >= float(level["min_inclusive"]):
            score = int(level["score"])
    return score


def score_impact(consequence: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    baseline = consequence["baseline"]
    risk = consequence["risk"]
    delta = consequence["delta"]
    baseline_cost = float(baseline["costs"]["total_cost_mln"])
    incremental_cost_pct = (
        max(0.0, float(delta["costs"]["total_cost_mln"])) / abs(baseline_cost) * 100.0
        if baseline_cost
        else 0.0
    )
    risk_demand = float(risk["total_demand_t"])
    shortage_share = (
        max(0.0, float(delta["total_shortage_t"])) / risk_demand if risk_demand else 0.0
    )
    values = {
        "critical_service_degradation_pp": max(
            0.0,
            -float(delta["minimum_annual_critical_service_delta"]) * 100.0,
        ),
        "shortage_share": shortage_share,
        "incremental_cost_pct": incremental_cost_pct,
        "hard_violation_count": float(max(0, int(delta["hard_violation_count"]))),
        "disruption_duration_months": float(max(0, int(delta["months_with_shortage"]))),
    }
    dimensions: dict[str, Any] = {}
    for name, value in values.items():
        score = _ordinal_score(value, config["impact_dimensions"][name])
        dimensions[name] = {"value": value, "score": score}
    impact_score = max(item["score"] for item in dimensions.values())
    return {
        "impact_score": impact_score,
        "aggregation": config["impact_aggregation"],
        "dimensions": dimensions,
        "provenance": {
            "status": "TEAM_ASSUMPTION_SCORING_RULE",
            "config_id": config.get("config_id"),
            "physical_consequences_source": "DIGITAL_TWIN_RESULT",
        },
    }


def score_likelihood(likelihood: dict[str, Any], config: dict[str, Any]) -> int | None:
    kind = likelihood.get("likelihood_type", "unknown")
    if kind == "unknown":
        return None
    if kind == "qualitative":
        return int(likelihood["score"])
    if kind == "probability":
        value = float(likelihood["value"])
    elif kind == "probability_range":
        method = config.get("probability_range_scoring", "upper_bound")
        if method != "upper_bound":
            raise RiskScoringError("Only upper_bound probability-range scoring is supported")
        value = float(likelihood["max"])
    else:
        return None
    for level in config["likelihood_probability_bands"]:
        if value <= float(level["max_inclusive"]):
            return int(level["score"])
    return 5


def build_risk_matrix(evaluations) -> dict[str, Any]:
    cells = {
        str(likelihood): {str(impact): [] for impact in range(1, 6)}
        for likelihood in range(1, 6)
    }
    unknown: list[dict[str, Any]] = []
    for evaluation in evaluations:
        item = {
            "risk_id": evaluation.risk.risk_id,
            "name": evaluation.risk.name,
            "impact_score": evaluation.impact["impact_score"],
        }
        if evaluation.likelihood_score is None:
            unknown.append(item)
        else:
            cells[str(evaluation.likelihood_score)][str(evaluation.impact["impact_score"])].append(item)
    return {
        "axes": {
            "likelihood": "ordinal 1..5",
            "impact": "ordinal 1..5",
        },
        "cells": cells,
        "unknown_likelihood": unknown,
        "note": "likelihood × impact is an ordinal prioritization score, not expected loss.",
    }
