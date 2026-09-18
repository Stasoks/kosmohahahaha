from kosmohak.domain.investment import commissioning_dates


def test_emergency_six_weeks_converts_to_two_months(case_data, assumptions):
    assert assumptions.source_delivery_lead_months(case_data.sources["E"]) == 2


def test_investment_commissioning_dates(plan, case_data, assumptions):
    dates = commissioning_dates(plan, case_data, assumptions)
    assert dates["ZBO"] == "2036-01"
    assert dates["EARTH_NEW"] == "2037-02"
    assert dates["LUNAR_ISRU"] == "2038-01"

