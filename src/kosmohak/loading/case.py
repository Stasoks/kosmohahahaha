from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from kosmohak.domain.case import (
    CaseData,
    ConstraintDefinition,
    DemandRow,
    InvestmentOption,
    StorageOption,
    SupplySource,
)


class CaseDataError(ValueError):
    pass


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise CaseDataError(f"Official data file is empty: {path}")
    return rows


def _schema(root: Path, filename: str) -> dict[str, Any]:
    return json.loads((root / "schemas" / filename).read_text(encoding="utf-8"))


def _validate_rows(rows: list[dict[str, Any]], schema: dict[str, Any], label: str) -> None:
    validator = Draft202012Validator(schema)
    for index, row in enumerate(rows, start=2):
        errors = sorted(validator.iter_errors(row), key=lambda item: list(item.path))
        if errors:
            raise CaseDataError(f"{label}:{index}: {errors[0].message}")


class CaseDataLoader:
    @classmethod
    def load(cls, root_path: str | Path) -> CaseData:
        root = Path(root_path).resolve()
        demand_raw = _read_csv(root / "data" / "demand.csv")
        demand_typed = [
            {
                "year": int(row["year"]),
                "base_total_t": float(row["base_total_t"]),
                "base_critical_t": float(row["base_critical_t"]),
                "low_total_t": float(row["low_total_t"]),
                "high_total_t": float(row["high_total_t"]),
                "status": row["status"],
            }
            for row in demand_raw
        ]
        _validate_rows(demand_typed, _schema(root, "demand.schema.json"), "data/demand.csv")
        demand = {row["year"]: DemandRow(**row) for row in demand_typed}
        if len(demand) != len(demand_typed):
            raise CaseDataError("data/demand.csv contains duplicate years")
        for row in demand.values():
            if row.base_critical_t > row.base_total_t:
                raise CaseDataError(f"Critical demand exceeds total demand in {row.year}")

        source_raw = _read_csv(root / "data" / "supply_sources.csv")
        source_typed = []
        for row in source_raw:
            source_typed.append(
                {
                    "source_id": row["source_id"],
                    "name": row["name"],
                    "capacity_t_per_year": float(row["capacity_t_per_year"]),
                    "variable_cost_mln_per_t": float(row["variable_cost_mln_per_t"]),
                    "reservation_rate_mln_per_t_year_capacity": float(row["reservation_rate_mln_per_t_year_capacity"]),
                    "take_or_pay_share": float(row["take_or_pay_share"]),
                    "lead_time_min_value": float(row["lead_time_min_value"]),
                    "lead_time_max_value": float(row["lead_time_max_value"]),
                    "lead_time_unit": row["lead_time_unit"],
                    "reliability_profile": row["reliability_profile"],
                    "available_from_year": int(row["available_from_year"]) if row["available_from_year"] else None,
                    "status": row["status"],
                    "notes": row["notes"],
                }
            )
        _validate_rows(source_typed, _schema(root, "supply_sources.schema.json"), "data/supply_sources.csv")
        official_availability_rules = {
            "C": {"type": "investment", "investment_id": "EARTH_NEW"},
            "D": {"type": "investment", "investment_id": "LUNAR_ISRU"},
        }
        sources = {
            row["source_id"]: SupplySource(
                **row,
                availability_rule=official_availability_rules.get(
                    row["source_id"],
                    {
                        "type": "calendar",
                        "available_from": (
                            f"{row['available_from_year']}-01"
                            if row["available_from_year"] is not None
                            else None
                        ),
                    },
                ),
                reliability_metadata={
                    "profile": row["reliability_profile"],
                    "semantics": "METADATA_ONLY",
                },
                provenance={
                    "status": "CASE_INPUT",
                    "scope": "OFFICIAL_CASE",
                    "source": "data/supply_sources.csv",
                },
            )
            for row in source_typed
        }
        if len(sources) != len(source_typed):
            raise CaseDataError("data/supply_sources.csv contains duplicate source IDs")
        names = {source.name: source.source_id for source in sources.values()}
        if len(names) != len(sources):
            raise CaseDataError("data/supply_sources.csv contains duplicate source names")
        for source in sources.values():
            if source.lead_time_max_value < source.lead_time_min_value:
                raise CaseDataError(f"Invalid lead-time range for source {source.source_id}")

        storage_rows = _read_csv(root / "data" / "storage_options.csv")
        storage = {
            row["storage_id"]: StorageOption(
                storage_id=row["storage_id"],
                name=row["name"],
                capacity_t=float(row["capacity_t"]),
                loss_rate_on_throughput=float(row["loss_rate_on_throughput"]),
                holding_cost_mln_per_t_year=float(row["holding_cost_mln_per_t_year"]),
                capex_mln=float(row["capex_mln"]),
                fixed_opex_mln_per_year=float(row["fixed_opex_mln_per_year"]),
                available_from_year=int(row["available_from_year"]),
                status=row["status"],
                notes=row["notes"],
            )
            for row in storage_rows
        }
        if len(storage) != len(storage_rows):
            raise CaseDataError("data/storage_options.csv contains duplicate storage IDs")
        for item in storage.values():
            if (
                item.capacity_t < 0
                or not 0 <= item.loss_rate_on_throughput <= 1
                or min(item.holding_cost_mln_per_t_year, item.capex_mln, item.fixed_opex_mln_per_year) < 0
                or item.status != "CASE_INPUT"
            ):
                raise CaseDataError(f"Invalid storage parameters for {item.storage_id}")

        investment_rows = _read_csv(root / "data" / "investment_options.csv")
        investments = {
            row["investment_id"]: InvestmentOption(
                investment_id=row["investment_id"],
                name=row["name"],
                option_fee_mln=float(row["option_fee_mln"]),
                exercise_cost_mln=float(row["exercise_cost_mln"]),
                total_capex_mln=float(row["total_capex_mln"]),
                commissioning_rule=row["commissioning_rule"],
                fixed_opex_mln_per_year=float(row["fixed_opex_mln_per_year"]),
                status=row["status"],
                notes=row["notes"],
            )
            for row in investment_rows
        }
        if len(investments) != len(investment_rows):
            raise CaseDataError("data/investment_options.csv contains duplicate investment IDs")
        for item in investments.values():
            if (
                min(item.option_fee_mln, item.exercise_cost_mln, item.total_capex_mln, item.fixed_opex_mln_per_year) < 0
                or item.status != "CASE_INPUT"
            ):
                raise CaseDataError(f"Negative investment value for {item.investment_id}")
        earth_new = investments.get("EARTH_NEW")
        if earth_new and abs(earth_new.option_fee_mln + earth_new.exercise_cost_mln - earth_new.total_capex_mln) > 1e-9:
            raise CaseDataError("EARTH_NEW total CAPEX must equal option fee plus exercise cost")

        constraint_rows = _read_csv(root / "data" / "constraints.csv")
        constraints = {
            row["constraint_id"]: ConstraintDefinition(
                constraint_id=row["constraint_id"],
                metric=row["metric"],
                operator=row["operator"],
                value=float(row["value"]),
                unit=row["unit"],
                period=row["period"],
                scenario=row["scenario"],
                severity=row["severity"],
                status=row["status"],
                description=row["description"],
            )
            for row in constraint_rows
        }
        if len(constraints) != len(constraint_rows):
            raise CaseDataError("data/constraints.csv contains duplicate constraint IDs")
        for item in constraints.values():
            if item.operator not in {"<=", ">="} or item.status != "CASE_INPUT":
                raise CaseDataError(f"Invalid constraint definition {item.constraint_id}")

        return CaseData(
            root=root,
            demand=demand,
            sources=sources,
            source_id_by_name=names,
            storage=storage,
            investments=investments,
            constraints=constraints,
            horizon_provenance={
                year: {
                    "status": "CASE_INPUT",
                    "scope": "OFFICIAL_CASE_HORIZON",
                    "source": "data/demand.csv",
                }
                for year in demand
            },
            workspace_provenance={
                "status": "CASE_INPUT",
                "scope": "OFFICIAL_CASE",
            },
        )
