from __future__ import annotations

import pytest

from kosmohak.loading import RiskLoader, RiskValidationError


def _raw(**updates):
    value = {
        "risk_id": "R1",
        "name": "Risk",
        "description": "test",
        "event": "event",
        "cause": "cause",
        "period_start": "2038-01",
        "period_end": "2038-12",
        "affected_parameters": ["availability_share"],
        "factor_changes": [
            {
                "factor": "availability_share",
                "source_id": "A",
                "value": 0.0,
                "status": "TEAM_ASSUMPTION",
            }
        ],
        "dependencies": [],
        "owner": "team",
        "likelihood": {"likelihood_type": "unknown"},
        "likelihood_status": "UNKNOWN",
        "source_references": [],
        "combination_policy": "apply_after_base",
        "metadata": {"status": "TEAM_ASSUMPTION"},
    }
    value.update(updates)
    return value


def test_unknown_likelihood_stays_unknown():
    risk = RiskLoader.from_dict(_raw())
    assert risk.likelihood["likelihood_type"] == "unknown"
    assert risk.likelihood_status == "UNKNOWN"


def test_unsubstantiated_probability_is_downgraded_to_unknown():
    risk = RiskLoader.from_dict(
        _raw(likelihood={"likelihood_type": "probability", "value": 0.04})
    )
    assert risk.likelihood["likelihood_type"] == "unknown"
    assert "declared_value" in risk.likelihood


def test_reliability_is_not_inferred_as_probability():
    risk = RiskLoader.from_dict(
        _raw(source_references=["reliability_profile=constant:0.96 metadata"])
    )
    assert risk.likelihood["likelihood_type"] == "unknown"
    assert "probability" not in risk.likelihood


def test_duplicate_same_shock_is_rejected():
    raw = _raw()
    raw["factor_changes"].append(dict(raw["factor_changes"][0]))
    with pytest.raises(RiskValidationError, match="duplicate"):
        RiskLoader.from_dict(raw)

