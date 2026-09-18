def holding_cost(
    opening_inventory_t: float,
    closing_inventory_t: float,
    annual_rate_mln_per_t: float,
    method: str,
) -> float:
    if method != "trapezoid":
        raise ValueError(f"Unsupported storage-average method: {method}")
    return ((opening_inventory_t + closing_inventory_t) / 2.0) * annual_rate_mln_per_t / 12.0


def discount_end_of_year(cost: float, year: int, base_year: int, real_rate: float) -> float:
    return cost / ((1.0 + real_rate) ** (year - base_year))

