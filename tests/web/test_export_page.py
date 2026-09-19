from __future__ import annotations

import io
import zipfile

import pytest

pytestmark = pytest.mark.web


def _download_labels(app):
    return [button.label for button in app.get("download_button")]


def test_plan_json_download_is_available(app, goto):
    goto("Данные и экспорт")
    assert "Скачать текущий план JSON" in _download_labels(app)


def test_preparing_exports_enables_downloads(app, by_label, goto):
    goto("Данные и экспорт")
    before = len(_download_labels(app))

    by_label(app.button, "Подготовить выгрузки").click().run()

    assert app.exception == []
    assert app.session_state["export_files"]
    downloads = _download_labels(app)
    assert len(downloads) > before
    assert any(label.endswith(".csv") for label in downloads)


def test_full_zip_bundle_is_valid(app, by_label, goto):
    goto("Данные и экспорт")
    by_label(app.button, "Подготовить полный ZIP").click().run()

    assert app.exception == []
    bundle = app.session_state["bundle"]
    assert bundle, "no bundle produced"
    payload = bytes(bundle)
    assert payload
    assert zipfile.is_zipfile(io.BytesIO(payload))
    assert any("ZIP" in label or "zip" in label for label in _download_labels(app))


def test_save_snapshot_stores_snapshot(app, by_label, goto):
    goto("Данные и экспорт")
    by_label(app.button, "Сохранить снимок").click().run()

    assert app.exception == []
    assert len(app.session_state["snapshots"]) >= 1
