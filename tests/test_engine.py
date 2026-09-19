from __future__ import annotations

import pytest

from kosmohak.simulation.physics import material_balance


def test_v01_material_balance() -> None:
    """Control vector V01: 10 + 30 - 2 - 25 = 13."""

    closing = material_balance(
        opening_inventory_t=10.0,
        delivered_t=30.0,
        losses_t=2.0,
        served_t=25.0,
    )
    assert closing == pytest.approx(13.0)
