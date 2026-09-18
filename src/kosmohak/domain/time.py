from __future__ import annotations


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-")
        year, month = int(year_text), int(month_text)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid month {value!r}; expected YYYY-MM") from exc
    if len(value) != 7 or not 1 <= month <= 12:
        raise ValueError(f"Invalid month {value!r}; expected YYYY-MM")
    return year, month


def add_months(value: str, months: int) -> str:
    year, month = parse_month(value)
    absolute = year * 12 + month - 1 + months
    return f"{absolute // 12:04d}-{absolute % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    output: list[str] = []
    current = start
    while current <= end:
        output.append(current)
        current = add_months(current, 1)
    return output

