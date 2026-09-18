from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemandService:
    served_critical_t: float
    served_noncritical_t: float
    shortage_critical_t: float
    shortage_noncritical_t: float
    closing_inventory_t: float


@dataclass(frozen=True)
class ThroughputFlow:
    gross_delivery_t: float
    losses_t: float
    net_delivery_t: float
    accepted_delivery_t: float
    overflow_t: float


def material_balance(
    opening_inventory_t: float,
    delivered_t: float,
    losses_t: float,
    served_t: float,
) -> float:
    return opening_inventory_t + delivered_t - losses_t - served_t


def serve_demand(
    available_inventory_t: float,
    total_demand_t: float,
    critical_demand_t: float,
) -> DemandService:
    critical_demand_t, noncritical_demand = split_demand(total_demand_t, critical_demand_t)
    critical = min(available_inventory_t, critical_demand_t)
    remaining = available_inventory_t - critical
    noncritical = min(remaining, noncritical_demand)
    closing = max(0.0, remaining - noncritical)
    return DemandService(
        served_critical_t=critical,
        served_noncritical_t=noncritical,
        shortage_critical_t=critical_demand_t - critical,
        shortage_noncritical_t=noncritical_demand - noncritical,
        closing_inventory_t=closing,
    )


def split_demand(total_demand_t: float, critical_demand_t: float) -> tuple[float, float]:
    if critical_demand_t > total_demand_t:
        raise ValueError("Critical demand is nested in total demand")
    return critical_demand_t, total_demand_t - critical_demand_t


def throughput_losses(gross_inflow_t: float, loss_rate: float) -> float:
    return gross_inflow_t * loss_rate


def accept_throughput(
    opening_inventory_t: float,
    gross_inflow_t: float,
    loss_rate: float,
    storage_capacity_t: float,
) -> ThroughputFlow:
    losses = throughput_losses(gross_inflow_t, loss_rate)
    post_loss = gross_inflow_t - losses
    free = max(0.0, storage_capacity_t - opening_inventory_t)
    accepted_net = min(post_loss, free)
    overflow = max(0.0, post_loss - accepted_net)
    return ThroughputFlow(
        gross_delivery_t=gross_inflow_t,
        losses_t=losses,
        net_delivery_t=post_loss,
        accepted_delivery_t=accepted_net,
        overflow_t=overflow,
    )


def reserve_tons(annual_total_demand_t: float, reserve_days: float, days_per_year: float = 365.0) -> float:
    return annual_total_demand_t * reserve_days / days_per_year


def apply_delivery_share(
    planned_delivery_t: float,
    actual_delivery_share: float,
    reliability_metadata: float | str | None = None,
) -> float:
    """Apply the declared scenario share once; reliability is intentionally metadata."""
    _ = reliability_metadata
    return planned_delivery_t * actual_delivery_share
