"""Consistent Russian presentation formatting for dashboard values."""
from __future__ import annotations

from typing import Any


def number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{digits}f}".replace(",", " ").replace(".", ",")


def money(value: Any, digits: int = 0) -> str:
    return f"{number(value, digits)} млн у.е."


def mass(value: Any, digits: int = 1) -> str:
    return f"{number(value, digits)} т"


def capacity(value: Any, digits: int = 1) -> str:
    return f"{number(value, digits)} т/год"


def percent(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{number(float(value) * 100, digits)}%"


def percentage_points(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{number(value, digits)} п.п."


def signed(value: Any, suffix: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if float(value) > 0 else ""
    tail = f" {suffix}" if suffix else ""
    return f"{sign}{number(value, digits)}{tail}"


def yes_no(value: Any) -> str:
    return "Да" if bool(value) else "Нет"
