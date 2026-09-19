from __future__ import annotations

import csv
import io
from typing import Iterable


HEADER_MAP = {
    "year": "Year",
    "month": "Month",
    "demand_total_t": "Demand_t",
    "demand_critical_t": "Demand_critical_t",
    "served_total_t": "Served_t",
    "served_critical_t": "Served_critical_t",
    "served_noncritical_t": "Served_noncritical_t",
    "total_service_level": "SL_total_pct",
    "critical_service_level": "SL_critical_pct",
    "opening_inventory_t": "Opening_inventory_t",
    "gross_supply_t": "Gross_supply_t",
    "gross_delivery_t": "Gross_delivery_t",
    "net_delivery_t": "Net_delivery_t",
    "accepted_delivery_t": "Accepted_delivery_t",
    "available_inventory_t": "Available_inventory_t",
    "closing_inventory_t": "Closing_inventory_t",
    "losses_t": "Losses_t",
    "losses_divided_by_throughput": "Loss_rate_pct",
    "active_loss_rate": "Active_loss_rate_pct",
    "overflow_t": "Overflow_t",
    "shortage_t": "Shortage_t",
    "critical_shortage_t": "Critical_shortage_t",
    "shortage_critical_t": "Shortage_critical_t",
    "shortage_noncritical_t": "Shortage_noncritical_t",
    "reserve_requirement_t": "Reserve_requirement_t",
    "reserve_actual_t": "Reserve_actual_t",
    "reserve_actual_days": "Reserve_actual_days",
    "active_storage_capacity_t": "Storage_capacity_t",
    "capex_mln": "CAPEX_mln",
    "fixed_opex_mln": "FixedOPEX_mln",
    "procurement_mln": "Procurement_mln",
    "reservation_mln": "Reservation_mln",
    "take_or_pay_effect_mln": "Take_or_pay_effect_mln",
    "take_or_pay_effect_in_procurement_mln": "Take_or_pay_effect_in_procurement_mln",
    "holding_mln": "Holding_mln",
    "initial_stock_cost_mln": "Initial_stock_cost_mln",
    "initial_stock_procurement_mln": "Initial_stock_procurement_mln",
    "initial_stock_reservation_mln": "Initial_stock_reservation_mln",
    "total_cost_mln": "TotalCost_mln",
    "discounted_cost_mln": "DiscountedCost_mln",
    "holding_cost_mln": "HoldingCost_mln",
    "reserved_capacity_t_per_year": "Reserved_capacity_t_per_year",
    "requested_order_t": "Requested_order_t",
    "feasible_order_t": "Feasible_order_t",
    "unfulfilled_request_t": "Unfulfilled_request_t",
    "planned_delivery_t": "Planned_delivery_t",
    "risk_underdelivery_t": "Risk_underdelivery_t",
    "delayed_delivery_t": "Delayed_delivery_t",
    "initial_stock_requested_t": "Initial_stock_requested_t",
    "initial_stock_feasible_t": "Initial_stock_feasible_t",
    "initial_stock_gross_delivery_t": "Initial_stock_gross_delivery_t",
    "initial_stock_losses_t": "Initial_stock_losses_t",
    "initial_stock_opening_inventory_t": "Initial_stock_opening_inventory_t",
    "payable_volume_t": "Payable_volume_t",
    "utilization": "Utilization_pct",
    "active_variable_price_mln_per_t": "Variable_price_mln_per_t",
    "ordered_payment_mln": "Ordered_payment_mln",
    "take_or_pay_extra_volume_t": "Take_or_pay_extra_volume_t",
    "take_or_pay_price_mln_per_t": "Take_or_pay_price_mln_per_t",
    "procurement_cost_mln": "Procurement_cost_mln",
    "reservation_cost_mln": "Reservation_cost_mln",
    "initial_stock_procurement_cost_mln": "Initial_stock_procurement_cost_mln",
    "initial_stock_reservation_cost_mln": "Initial_stock_reservation_cost_mln",
}

PERCENT_FIELDS = {
    "total_service_level",
    "critical_service_level",
    "losses_divided_by_throughput",
    "active_loss_rate",
    "utilization",
}


def _percent(value: str) -> str:
    if value == "":
        return value
    try:
        return f"{float(value) * 100:.10g}"
    except ValueError:
        return value


def csv_with_unit_headers(payload: bytes) -> bytes:
    """Make Streamlit CSV downloads self-describing without changing core exports."""

    text = payload.decode("utf-8-sig")
    if not text.strip():
        return payload

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return payload

    output = io.StringIO()
    renamed = [HEADER_MAP.get(field, field) for field in reader.fieldnames]
    writer = csv.DictWriter(output, fieldnames=renamed, lineterminator="\n")
    writer.writeheader()

    for row in reader:
        converted = {}
        for field in reader.fieldnames:
            value = row.get(field, "")
            if field in PERCENT_FIELDS:
                value = _percent(value)
            converted[HEADER_MAP.get(field, field)] = value
        writer.writerow(converted)

    return output.getvalue().encode("utf-8")
