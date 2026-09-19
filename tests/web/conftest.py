"""Fixtures for headless Streamlit UI tests.

These tests drive the real dashboard through ``streamlit.testing.v1.AppTest``,
so widget wiring, session-state lifecycle and the export buttons are exercised
end to end without a browser.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP = ROOT / "streamlit_app.py"

PAGES = [
    "Обзор",
    "Стратегия",
    "Результаты",
    "Сценарии",
    "Риски и чувствительность",
    "Исследования",
    "Данные и экспорт",
]


def _clear_caches() -> None:
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()


def _labeled(elements, label):
    for element in elements or []:
        if getattr(element, "label", None) == label:
            return element
    available = [getattr(element, "label", None) for element in (elements or [])]
    raise AssertionError(f"no widget labelled {label!r}; available: {available}")


def _visible_text(at) -> str:
    parts: list[str] = []
    for name in ("title", "header", "subheader", "markdown", "caption", "success", "warning", "error", "info"):
        for element in getattr(at, name, []) or []:
            value = getattr(element, "value", None)
            if value is None:
                value = getattr(element, "body", "")
            parts.append(str(value))
    return "\n".join(parts)


@pytest.fixture(autouse=True)
def isolated_streamlit_caches():
    """Keep cached backend calls from leaking between UI tests."""

    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    return at


@pytest.fixture
def goto(app):
    """Navigate the sidebar to a page by its label and return the AppTest."""

    def _goto(label: str):
        app.radio[0].set_value(label).run()
        assert app.exception == [], f"Page {label!r} raised: {app.exception}"
        return app

    return _goto


@pytest.fixture
def by_label():
    return _labeled


@pytest.fixture
def visible_text():
    return _visible_text


@pytest.fixture
def pages():
    return list(PAGES)
