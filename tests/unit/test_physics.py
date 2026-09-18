import pytest

from kosmohak.simulation.physics import accept_throughput, serve_demand


def test_losses_apply_once_to_gross_throughput():
    flow = accept_throughput(0, 20, 0.05, 100)
    assert flow.losses_t == pytest.approx(1)
    assert flow.accepted_delivery_t == pytest.approx(19)


def test_overflow_keeps_inventory_physical():
    flow = accept_throughput(9, 10, 0.1, 10)
    assert flow.losses_t == pytest.approx(1)
    assert flow.accepted_delivery_t == pytest.approx(1)
    assert flow.overflow_t == pytest.approx(8)


def test_critical_service_has_priority():
    service = serve_demand(5, total_demand_t=10, critical_demand_t=7)
    assert service.served_critical_t == 5
    assert service.served_noncritical_t == 0
    assert service.closing_inventory_t == 0
