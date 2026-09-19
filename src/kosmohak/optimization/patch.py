from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any

from kosmohak.domain.plan import OperatorPlan


@dataclass(frozen=True)
class PlanChange:
    path: str
    old: Any
    new: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanPatch:
    changes: tuple[PlanChange, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"changes": [item.to_dict() for item in self.changes]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PlanPatch":
        return cls(tuple(PlanChange(**item) for item in value.get("changes", [])))


def _orders(raw: dict) -> dict[str, dict]:
    return {
        str(item["source_id"]): {
            "mode": item["mode"],
            "values": {str(key): value for key, value in item.get("values", {}).items()},
        }
        for item in raw["decisions"].get("supply_orders", [])
    }


def _reservations(raw: dict) -> dict[tuple[str, str], Any]:
    return {
        (str(item["source_id"]), str(item["year"])): item["reserved_capacity_t"]
        for item in raw["decisions"].get("capacity_reservations", [])
    }


def _investments(raw: dict) -> dict[str, dict]:
    return {
        str(item["investment_id"]): {
            key: value for key, value in item.items() if key != "investment_id"
        }
        for item in raw["decisions"].get("investments", [])
    }


def _mapping_changes(prefix: str, before: dict, after: dict) -> list[PlanChange]:
    changes: list[PlanChange] = []
    for key in sorted(set(before) | set(after), key=str):
        old, new = before.get(key), after.get(key)
        path = f"{prefix}.{key}"
        if isinstance(old, dict) and isinstance(new, dict):
            changes.extend(_mapping_changes(path, old, new))
        elif old != new:
            changes.append(PlanChange(path, copy.deepcopy(old), copy.deepcopy(new)))
    return changes


def diff_plans(before: OperatorPlan | dict, after: OperatorPlan | dict) -> PlanPatch:
    old = before.raw if isinstance(before, OperatorPlan) else before
    new = after.raw if isinstance(after, OperatorPlan) else after
    changes: list[PlanChange] = []
    old_orders, new_orders = _orders(old), _orders(new)
    for source_id in sorted(set(old_orders) | set(new_orders)):
        a, b = old_orders.get(source_id, {}), new_orders.get(source_id, {})
        if a.get("mode") != b.get("mode"):
            changes.append(PlanChange(f"orders.{source_id}.mode", a.get("mode"), b.get("mode")))
        changes.extend(
            _mapping_changes(
                f"orders.{source_id}.values",
                a.get("values", {}),
                b.get("values", {}),
            )
        )
    old_res, new_res = _reservations(old), _reservations(new)
    for key in sorted(set(old_res) | set(new_res)):
        if old_res.get(key) != new_res.get(key):
            changes.append(
                PlanChange(
                    f"reservations.{key[0]}.{key[1]}",
                    old_res.get(key),
                    new_res.get(key),
                )
            )
    old_inv, new_inv = _investments(old), _investments(new)
    for investment_id in sorted(set(old_inv) | set(new_inv)):
        changes.extend(
            _mapping_changes(
                f"investments.{investment_id}",
                old_inv.get(investment_id, {}),
                new_inv.get(investment_id, {}),
            )
        )
    decisions_old, decisions_new = old["decisions"], new["decisions"]
    changes.extend(
        _mapping_changes(
            "initial_stock",
            decisions_old.get("initial_stock_acquisition") or {},
            decisions_new.get("initial_stock_acquisition") or {},
        )
    )
    changes.extend(
        _mapping_changes(
            "emergency_role",
            decisions_old.get("emergency_role_by_year", {}),
            decisions_new.get("emergency_role_by_year", {}),
        )
    )
    changes.extend(
        _mapping_changes(
            "inventory_policy",
            decisions_old.get("inventory_policy", {}),
            decisions_new.get("inventory_policy", {}),
        )
    )
    return PlanPatch(tuple(sorted(changes, key=lambda item: item.path)))


def apply_plan_patch(
    plan: OperatorPlan | dict,
    patch: PlanPatch,
    *,
    plan_id: str | None = None,
) -> dict:
    raw = copy.deepcopy(plan.raw if isinstance(plan, OperatorPlan) else plan)
    decisions = raw["decisions"]
    for change in patch.changes:
        parts = change.path.split(".")
        section = parts[0]
        if section == "orders":
            source_id, field = parts[1], parts[2]
            item = next(
                (row for row in decisions["supply_orders"] if str(row["source_id"]) == source_id),
                None,
            )
            if item is None:
                item = {"source_id": source_id, "mode": "annual_even", "values": {}}
                decisions["supply_orders"].append(item)
            if field == "mode":
                item["mode"] = change.new
            else:
                period = ".".join(parts[3:])
                if change.new is None:
                    item.setdefault("values", {}).pop(period, None)
                else:
                    item.setdefault("values", {})[period] = change.new
        elif section == "reservations":
            source_id, year = parts[1], int(parts[2])
            item = next(
                (
                    row for row in decisions["capacity_reservations"]
                    if str(row["source_id"]) == source_id and int(row["year"]) == year
                ),
                None,
            )
            if change.new is None and item is not None:
                decisions["capacity_reservations"].remove(item)
            elif item is None:
                decisions["capacity_reservations"].append(
                    {"source_id": source_id, "year": year, "reserved_capacity_t": change.new}
                )
            else:
                item["reserved_capacity_t"] = change.new
        elif section == "investments":
            investment_id, field = parts[1], ".".join(parts[2:])
            item = next(
                (row for row in decisions["investments"] if str(row["investment_id"]) == investment_id),
                None,
            )
            if item is None:
                item = {"investment_id": investment_id}
                decisions["investments"].append(item)
            if change.new is None:
                item.pop(field, None)
            else:
                item[field] = change.new
        else:
            roots = {
                "initial_stock": "initial_stock_acquisition",
                "emergency_role": "emergency_role_by_year",
                "inventory_policy": "inventory_policy",
            }
            target = decisions.setdefault(roots[section], {})
            for key in parts[1:-1]:
                target = target.setdefault(key, {})
            key = parts[-1]
            if change.new is None:
                target.pop(key, None)
            else:
                target[key] = copy.deepcopy(change.new)
    if plan_id is not None:
        raw["plan_id"] = plan_id
    return raw
