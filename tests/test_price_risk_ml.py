from datetime import date, timedelta

from src.geri.price_risk_ml import build_price_risk_forecast


def _history(days=90):
    start = date(2026, 1, 1)
    oil = []
    ttf = []
    vix = []
    geri = []
    for index in range(days):
        day = start + timedelta(days=index)
        risk_wave = ((index % 18) - 9) * 0.7
        geri_value = 36 + risk_wave + index * 0.08
        oil.append({
            "date": day,
            "brent_price": 70 + index * 0.11 + risk_wave * 0.25,
            "wti_price": 66 + index * 0.1 + risk_wave * 0.2,
        })
        ttf.append({
            "date": day,
            "ttf_price": 31 + index * 0.04 + risk_wave * 0.15,
        })
        vix.append({
            "date": day,
            "vix_close": 17 + abs(risk_wave) * 0.2,
        })
        geri.append({"date": day, "value": round(geri_value)})
    return oil, ttf, vix, geri


def test_price_risk_model_returns_all_requested_forecasts():
    oil, ttf, vix, geri = _history()
    result = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[
            {"key": "brent", "change_pct": 0.4},
            {"key": "wti", "change_pct": 0.3},
            {"key": "ttf", "change_pct": -0.2},
            {"key": "vix", "change_pct": 0.5},
        ],
        geri_value=42,
        geri_trend_pct=6,
    )

    assert result["status"] in {"ready", "research_only"}
    assert result["sample_size"] >= 80
    assert result["brent_1_3d"]["rise_probability"] is not None
    assert result["brent_1_3d"]["fall_probability"] is not None
    assert result["risk_regime"]["elevated_24h"] == 100.0
    assert result["brent_next_day"]["direction"] in {"higher", "lower", "range-bound"}
    assert result["ttf_next_day"]["direction"] in {"higher", "lower", "range-bound"}
    assert result["significant_move"]["probability"] is not None
    assert result["higher_risk_band"]["probability"] is not None
    assert result["underpriced_risk"]["probability"] is not None
    assert "executive_summary" in result["analysis"]
    assert result["validation"]["brent_direction"]["observations"] > 0
    assert result["validation"]["brent_direction"]["accuracy_pct"] is not None
    assert result["validation"]["brent_direction"]["baseline_brier_score"] is not None
    assert "model_validation" in result["analysis"]
    assert "not guarantees" in result["analysis"]["limitations"]


def test_price_risk_model_reports_insufficient_history_without_inventing_forecasts():
    oil, ttf, vix, geri = _history(days=6)
    result = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[],
        geri_value=20,
        geri_trend_pct=0,
    )

    assert result["status"] == "insufficient_data"
    assert result["confidence"] == "insufficient"
    assert "brent_1_3d" not in result


def test_validation_underperformance_prevents_high_confidence_label():
    oil, ttf, vix, geri = _history()
    result = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[
            {"key": "brent", "change_pct": 0},
            {"key": "wti", "change_pct": 0},
            {"key": "ttf", "change_pct": 0},
            {"key": "vix", "change_pct": 0},
        ],
        geri_value=40,
        geri_trend_pct=0,
    )

    for validation in result["validation"].values():
        validation["accuracy_pct"] = 40
        validation["baseline_accuracy_pct"] = 60
    from src.geri.price_risk_ml import _confidence
    assert _confidence(result["sample_size"], result["validation"]) == "low"


def test_training_requires_complete_three_period_horizons_and_aligned_features():
    oil, ttf, vix, geri = _history(days=20)
    ttf = [row for index, row in enumerate(ttf) if index != 10]
    result = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[],
        geri_value=40,
        geri_trend_pct=0,
    )

    assert result["sample_size"] < 16


def test_intraday_signal_gaps_do_not_change_daily_model_inference():
    oil, ttf, vix, geri = _history()
    complete = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[
            {"key": "brent", "change_pct": 0.4},
            {"key": "wti", "change_pct": 0.3},
            {"key": "ttf", "change_pct": -0.2},
        ],
        geri_value=42,
        geri_trend_pct=6,
    )
    missing_live_vix = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[
            {"key": "brent", "change_pct": 15},
            {"key": "wti", "change_pct": -12},
            {"key": "ttf", "change_pct": 8},
        ],
        geri_value=90,
        geri_trend_pct=30,
    )

    assert complete["forecast_as_of"] == missing_live_vix["forecast_as_of"]
    assert complete["brent_1_3d"] == missing_live_vix["brent_1_3d"]


def test_today_partial_rows_are_excluded_from_daily_inference():
    from datetime import datetime, timezone

    oil, ttf, vix, geri = _history()
    today = datetime.now(timezone.utc).date()
    oil.append({"date": today, "brent_price": 999, "wti_price": 999})
    ttf.append({"date": today, "ttf_price": 999})
    vix.append({"date": today, "vix_close": 99})
    geri.append({"date": today, "value": 99})
    result = build_price_risk_forecast(
        oil_rows=oil,
        ttf_rows=ttf,
        vix_rows=vix,
        geri_rows=geri,
        current_signals=[],
        geri_value=99,
        geri_trend_pct=99,
    )

    assert result["forecast_as_of"] != today.isoformat()