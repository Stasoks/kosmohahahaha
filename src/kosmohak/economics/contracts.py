from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractCost:
    payable_volume_t: float
    variable_payment_mln: float
    reservation_payment_mln: float
    take_or_pay_effect_mln: float


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
    )

