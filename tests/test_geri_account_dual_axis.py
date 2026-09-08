from pathlib import Path


ACCOUNT_HTML = Path("src/static/users-account.html")


def test_geri_market_overlays_use_raw_values_on_right_axis():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    assert "normalizeToScale" not in html
    assert "assetNormalizationRanges" not in html
    assert "return rawVal;" in html
    assert "yAxisID: 'y1'" in html
    assert "GERI — Risk Index (0–100)" in html


def test_geri_right_axis_uses_asset_specific_units():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    for axis_title in (
        "Brent Oil — USD/barrel",
        "TTF Gas — €/MWh",
        "VIX Index",
        "EUR/USD",
        "EU Storage — % Full",
    ):
        assert axis_title in html

    assert "rightAxis.display = Boolean(rightConfig);" in html
    assert "rightAxis.title.text = rightConfig ? rightConfig.axisTitle : '';" in html


def test_geri_chart_allows_only_one_unit_specific_overlay_at_a_time():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    assert "toggles.forEach(otherToggle => otherToggle.classList.remove('active'));" in html
    assert "marketOverlays[key].active = false;" in html