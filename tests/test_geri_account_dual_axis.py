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


def test_geri_chart_exposes_three_analysis_modes():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    assert 'data-mode="price"' in html
    assert 'data-mode="change"' in html
    assert 'data-mode="relationship"' in html
    assert ">Price</button>" in html
    assert ">% Change</button>" in html
    assert ">Risk Relationship</button>" in html


def test_geri_change_mode_compares_points_with_market_percent():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    assert "function dailyPointChanges(values)" in html
    assert "function dailyPercentChanges(values)" in html
    assert "dailyPointChanges(geriHistoryData.map(point => point.value))" in html
    assert "let previous = null;" in html
    assert "GERI Daily Change — Points" in html
    assert "Daily % Change" in html
    assert "changeUnit: currentGeriAnalysisMode === 'price' ? null : 'points'" in html


def test_geri_relationship_mode_classifies_all_direction_pairs():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    for relationship in (
        "GERI ↑ + Market ↑ — risk signal confirmed",
        "GERI ↑ + Market ↓ — bearish divergence",
        "GERI ↓ + Market ↑ — bullish divergence",
        "GERI ↓ + Market ↓ — easing risk confirmed",
    ):
        assert relationship in html

    assert "type: currentGeriAnalysisMode === 'relationship' ? 'bar' : 'line'" in html
    assert "relationshipData: relationshipData" in html


def test_geri_price_chart_uses_official_five_regime_bands():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    for definition in (
        "{ min: 0, max: 20, label: 'LOW'",
        "{ min: 20, max: 40, label: 'MODERATE'",
        "{ min: 40, max: 60, label: 'ELEVATED'",
        "{ min: 60, max: 80, label: 'SEVERE'",
        "{ min: 80, max: 100, label: 'CRITICAL'",
    ):
        assert definition in html

    assert "ctx.fillText(band.label, chartArea.left + 8, y);" in html
    assert "if (value >= 81) return 'CRITICAL';" in html
    assert "if (value >= 61) return 'SEVERE';" in html
    assert "if (value >= 41) return 'ELEVATED';" in html
    assert "if (value >= 21) return 'MODERATE';" in html
    assert "const band = getGeriBandForValue(val);" in html


def test_geri_significant_moves_use_hoverable_triangle_markers():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    assert "Math.abs(delta) < 8" in html
    assert "pointStyle: 'triangle'" in html
    assert "event.direction === 'down' ? 180 : 0" in html
    assert "arrow + ' ' + formatSignedChange(event.delta, 0) + ' points'" in html
    assert "'Primary driver: ' + event.driver" in html
    assert "'Brent: ' + formatSignedChange(event.brentChange, 1) + '%'" in html
    assert "'TTF: ' + formatSignedChange(event.ttfChange, 1) + '%'" in html
    assert "'VIX: ' + formatSignedChange(event.vixChange, 1) + '%'" in html


def test_geri_direct_annotations_are_limited_to_exceptional_events():
    html = ACCOUNT_HTML.read_text(encoding="utf-8")

    assert "Largest GERI spike" in html
    assert "Largest GERI drop" in html
    assert "Major escalation" in html
    assert "Major de-escalation" in html
    assert "exceptional.slice(0, 5)" in html
    assert "annotText = 'Risk spike'" not in html
    assert "annotText = 'Risk drop'" not in html