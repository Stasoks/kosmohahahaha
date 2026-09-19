from __future__ import annotations

import csv
import io

from app.export_csv import csv_with_unit_headers


def test_streamlit_csv_headers_include_units_and_percent_values() -> None:
    payload = (
        "year,demand_total_t,total_service_level,critical_service_level,capex_mln\n"
        "2040,390,0.97,0.99,180\n"
    ).encode("utf-8")

    converted = csv_with_unit_headers(payload)
    reader = csv.DictReader(io.StringIO(converted.decode("utf-8")))
    row = next(reader)

    assert reader.fieldnames == [
        "Year",
        "Demand_t",
        "SL_total_pct",
        "SL_critical_pct",
        "CAPEX_mln",
    ]
    assert row["Demand_t"] == "390"
    assert row["SL_total_pct"] == "97"
    assert row["SL_critical_pct"] == "99"
    assert row["CAPEX_mln"] == "180"
