from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def test_app_boots_with_default_plan_and_result(app):
    assert app.exception == []
    assert app.session_state["plan"]["plan_id"] == "final-base-plan"
    assert app.session_state["result"]["plan_hash"]
    assert app.session_state["result"]["BASE"]["summary"]["valid"] is True


def test_sidebar_reports_actual_calculation(app):
    rendered = "\n".join(item.value for item in app.success)
    assert "Расчёт актуален" in rendered
    assert any("Текущая стратегия" in block.value for block in app.markdown)
