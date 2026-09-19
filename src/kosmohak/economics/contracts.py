from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractCost:
    payable_volume_t: float
    variable_payment_mln: float
    reservation_payment_mln: float
    take_or_pay_effect_mln: float
    ordered_payment_mln: float = 0.0
    take_or_pay_extra_volume_t: float = 0.0
    effective_variable_price_mln_per_t: float = 0.0
    take_or_pay_price_mln_per_t: float = 0.0


def reservation_payment(
    annual_reserved_capacity_t: float,
    reservation_rate_mln_per_t_year_capacity: float,
    period_fraction: float,
) -> float:
    return annual_reserved_capacity_t * reservation_rate_mln_per_t_year_capacity * period_fraction


def contract_cost(
    *,
    ordered_volume_t: float,
    reserved_capacity_period_t: float,
    take_or_pay_share: float,
    variable_price_mln_per_t: float,
    annual_reserved_capacity_t: float,
    reservation_rate_mln_per_t_year_capacity: float,
    period_fraction: float,
) -> ContractCost:
    payable = max(ordered_volume_t, take_or_pay_share * reserved_capacity_period_t)
    variable = payable * variable_price_mln_per_t
    ordered_payment = ordered_volume_t * variable_price_mln_per_t
    return ContractCost(
        payable_volume_t=payable,
        variable_payment_mln=variable,
        reservation_payment_mln=reservation_payment(
            annual_reserved_capacity_t,
            reservation_rate_mln_per_t_year_capacity,
            period_fraction,
        ),
        take_or_pay_effect_mln=max(0.0, variable - ordered_payment),
        ordered_payment_mln=ordered_payment,
        take_or_pay_extra_volume_t=max(0.0, payable - ordered_volume_t),
        effective_variable_price_mln_per_t=(variable / payable if payable else variable_price_mln_per_t),
        take_or_pay_price_mln_per_t=variable_price_mln_per_t,
    )


def priced_contract_cost(
    *,
    ordered_by_month_t: dict[str, float],
    variable_price_by_month_mln_per_t: dict[str, float],
    active_months: list[str] | tuple[str, ...],
    reserved_capacity_period_t: float,
    take_or_pay_share: float,
    annual_reserved_capacity_t: float,
    reservation_rate_by_month_mln_per_t_year_capacity: dict[str, float],
) -> ContractCost:
    """Charge orders at order-month prices and TOP-only volume at the active-period rate."""
    ordered = sum(float(value) for value in ordered_by_month_t.values())
    ordered_payment = sum(
        float(volume) * float(variable_price_by_month_mln_per_t[month])
        for month, volume in ordered_by_month_t.items()
    )
    payable = max(ordered, take_or_pay_share * reserved_capacity_period_t)
    extra = max(0.0, payable - ordered)
    active_prices = [
        float(variable_price_by_month_mln_per_t[month]) for month in active_months
    ]
    if active_prices:
        top_price = sum(active_prices) / len(active_prices)
    elif ordered:
        top_price = ordered_payment / ordered
    else:
        top_price = 0.0
    top_effect = extra * top_price
    variable_payment = ordered_payment + top_effect
    reservation = sum(
        annual_reserved_capacity_t
        * float(reservation_rate_by_month_mln_per_t_year_capacity[month])
        / 12.0
        for month in active_months
    )
    return ContractCost(
        payable_volume_t=payable,
        variable_payment_mln=variable_payment,
        reservation_payment_mln=reservation,
        take_or_pay_effect_mln=top_effect,
        ordered_payment_mln=ordered_payment,
        take_or_pay_extra_volume_t=extra,
        effective_variable_price_mln_per_t=(
            variable_payment / payable if payable else top_price
        ),
        take_or_pay_price_mln_per_t=top_price,
    )
