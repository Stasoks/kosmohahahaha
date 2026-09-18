from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    source_id: str
    source_name: str
    order_month: str
    requested_t: float
    feasible_t: float
    unfulfilled_request_t: float
    planned_arrival_month: str
    actual_arrival_month: str
    actual_delivery_share: float
    availability_share: float
    gross_delivery_t: float

    def to_dict(self) -> dict:
        return asdict(self)
