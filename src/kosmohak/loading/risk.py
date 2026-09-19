from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kosmohak.domain.risk import RiskDefinition
from kosmohak.domain.time import parse_month
from kosmohak.simulation.environment import SUPPORTED_RISK_FACTORS


class RiskValidationError(ValueError):
    pass


def _numeric_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield float(item)
    else:
        yield float(value)


def _validate_factor_value(risk_id: str, factor: str, value: Any) -> None:
    values = list(_numeric_values(value))
    shares = {"actual_delivery_share", "availability_share", "storage_loss_rate_override"}
    nonnegative = SUPPORTED_RISK_FACTORS - shares
    if factor in shares and any(not 0 <= item <= 1 for item in values):
        raise RiskValidationError(f"{risk_id}: {factor} values must be within 0..1")
    if factor in nonnegative and any(item < 0 for item in values):
        raise RiskValidationError(f"{risk_id}: {factor} values cannot be negative")


def _period(value: Any, field: str, *, end: bool = False) -> str:
    text = str(value)
    if len(text) == 4 and text.isdigit():
        text = f"{text}-{'12' if end else '01'}"
    try:
        parse_month(text[:7])
    except ValueError as exc:
        raise RiskValidationError(f"{field} must be YYYY or YYYY-MM") from exc
    return text[:7]


def _normalize_likelihood(raw: Any, fallback_basis: Any, fallback_status: Any) -> tuple[dict[str, Any], str | None, str]:
    value = dict(raw) if isinstance(raw, dict) else {"likelihood_type": "unknown"}
    kind = str(value.get("likelihood_type", value.get("type", "unknown"))).lower()
    basis = value.get("basis", fallback_basis)
    source = value.get("source")
    if kind not in {"probability", "probability_range", "qualitative", "unknown"}:
        raise RiskValidationError(f"Unsupported likelihood_type: {kind}")
    if kind != "unknown" and (not basis or not source):
        return {
            "likelihood_type": "unknown",
            "reason": "Likelihood basis and source are both required for scoring.",
            "declared_value": value,
        }, str(basis) if basis else None, "UNKNOWN"
    if kind == "probability":
        probability = float(value["value"])
        if not 0 <= probability <= 1:
            raise RiskValidationError("Probability likelihood must be within 0..1")
    elif kind == "probability_range":
        minimum, maximum = float(value["min"]), float(value["max"])
        if not 0 <= minimum <= maximum <= 1:
            raise RiskValidationError("Probability range must satisfy 0 <= min <= max <= 1")
    elif kind == "qualitative":
        score = int(value["score"])
        if not 1 <= score <= 5:
            raise RiskValidationError("Qualitative likelihood score must be within 1..5")
    value["likelihood_type"] = kind
    value.setdefault("basis", basis)
    return value, str(basis) if basis else None, str(fallback_status or ("UNKNOWN" if kind == "unknown" else "TEAM_ASSUMPTION"))


class RiskLoader:
    @classmethod
    def load(cls, path: str | Path) -> list[RiskDefinition]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        envelope_status = raw.get("status") if isinstance(raw, dict) else None
        items = raw.get("risks", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise RiskValidationError("Risk file must be an array or an object with a risks array")
        risks = [cls.from_dict(item, default_status=envelope_status) for item in items]
        ids = [item.risk_id for item in risks]
        if len(ids) != len(set(ids)):
            raise RiskValidationError("Duplicate risk_id")
        return risks

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, default_status: str | None = None) -> RiskDefinition:
        status = str(raw.get("status", raw.get("metadata", {}).get("status", default_status or "TEAM_ASSUMPTION")))
        if status not in {"CASE_INPUT", "TEAM_ASSUMPTION"}:
            raise RiskValidationError("Risk status must be CASE_INPUT or TEAM_ASSUMPTION")
        risk_id = str(raw.get("risk_id", "")).strip()
        if not risk_id:
            raise RiskValidationError("risk_id is required")
        start = _period(raw.get("period_start"), f"{risk_id}.period_start")
        end = _period(raw.get("period_end"), f"{risk_id}.period_end", end=True)
        if end < start:
            raise RiskValidationError(f"{risk_id}: period_end precedes period_start")
        changes_raw = raw.get("factor_changes", [])
        if not isinstance(changes_raw, list) or not changes_raw:
            raise RiskValidationError(f"{risk_id}: factor_changes must be a non-empty array")
        changes: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for item in changes_raw:
            change = dict(item)
            factor = str(change.get("factor", ""))
            if factor not in SUPPORTED_RISK_FACTORS:
                raise RiskValidationError(f"{risk_id}: unsupported risk factor {factor!r}")
            change_status = str(change.get("status", status))
            if change_status not in {"CASE_INPUT", "TEAM_ASSUMPTION"}:
                raise RiskValidationError(f"{risk_id}: invalid factor provenance status")
            change["status"] = change_status
            change_start = _period(change.get("period_start", start), f"{risk_id}.{factor}.period_start")
            change_end = _period(change.get("period_end", end), f"{risk_id}.{factor}.period_end", end=True)
            change["period_start"], change["period_end"] = change_start, change_end
            if not any(key in change for key in ("value", "multiplier", "override", "additional_months")):
                raise RiskValidationError(f"{risk_id}: factor {factor} has no value")
            raw_value = next(
                change[key]
                for key in ("value", "multiplier", "override", "additional_months")
                if key in change
            )
            _validate_factor_value(risk_id, factor, raw_value)
            target = str(change.get("source_id", change.get("source_name", change.get("storage_id", change.get("investment_id", change.get("target_id", "*"))))))
            key = (factor, target, change_start, change_end)
            if key in seen:
                raise RiskValidationError(f"{risk_id}: duplicate overlapping override {factor}/{target}")
            seen.add(key)
            changes.append(change)
        likelihood, basis, likelihood_status = _normalize_likelihood(
            raw.get("likelihood"), raw.get("likelihood_basis"), raw.get("likelihood_status")
        )
        affected = raw.get("affected_parameters") or [item["factor"] for item in changes]
        return RiskDefinition(
            risk_id=risk_id,
            name=str(raw.get("name", risk_id)),
            description=str(raw.get("description", "")),
            event=str(raw.get("event", "")),
            cause=str(raw.get("cause", "")),
            period_start=start,
            period_end=end,
            affected_parameters=tuple(str(item) for item in affected),
            factor_changes=tuple(changes),
            dependencies=tuple(str(item) for item in raw.get("dependencies", [])),
            owner=str(raw.get("owner", "unassigned")),
            likelihood=likelihood,
            likelihood_basis=basis,
            likelihood_status=likelihood_status,
            source_references=tuple(str(item) for item in raw.get("source_references", [])),
            combination_policy=str(raw.get("combination_policy", "apply_after_base")),
            mitigation=dict(raw["mitigation"]) if raw.get("mitigation") else None,
            anticipated_consequence=str(raw.get("anticipated_consequence", "Computed by digital twin.")),
            residual_consequence_statement=str(raw.get("residual_consequence", "Not quantified without an explicit mitigation plan patch.")),
            stakeholder_ids=tuple(str(item) for item in raw.get("stakeholder_ids", [])),
            metadata=dict(raw.get("metadata", {})),
            status=status,
            raw=dict(raw),
        )
