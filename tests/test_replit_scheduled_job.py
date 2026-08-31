from scripts import replit_scheduled_job


def test_alerts_run_once_before_deliveries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: "token",
    )

    def fake_invoke(name, _handler_name, _token, **_kwargs):
        calls.append(name)
        return 200

    monkeypatch.setattr(replit_scheduled_job, "_invoke", fake_invoke)

    replit_scheduled_job.run_job("alerts")

    assert calls == ["alerts", "pro_delivery", "trader_delivery"]


def test_busy_alerts_do_not_launch_deliveries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: "token",
    )

    def fake_invoke(name, _handler_name, _token, **_kwargs):
        calls.append(name)
        return 409

    monkeypatch.setattr(replit_scheduled_job, "_invoke", fake_invoke)

    replit_scheduled_job.run_job("alerts")

    assert calls == ["alerts"]


def test_named_job_uses_expected_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: "token",
    )

    def fake_invoke(name, handler_name, _token, **_kwargs):
        calls.append((name, handler_name))
        return 200

    monkeypatch.setattr(replit_scheduled_job, "_invoke", fake_invoke)

    replit_scheduled_job.run_job("intraday")

    assert calls == [
        ("intraday", "run_intraday_price_capture"),
    ]


def test_job_controls_are_read_from_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: "token",
    )
    monkeypatch.setenv("SKIP_AI", "true")
    monkeypatch.setenv("SKIP_RISK", "true")

    def fake_invoke(name, handler_name, _token, **kwargs):
        calls.append((name, handler_name, kwargs))
        return 200

    monkeypatch.setattr(replit_scheduled_job, "_invoke", fake_invoke)

    replit_scheduled_job.run_job("ingestion")

    assert calls == [
        (
            "ingestion",
            "run_ingestion_pipeline",
            {"skip_ai": True, "skip_risk": True},
        ),
    ]


def test_alert_dry_run_never_launches_delivery_handlers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: "token",
    )
    monkeypatch.setenv("DRY_RUN", "true")

    def fake_invoke(name, _handler_name, _token, **_kwargs):
        calls.append(name)
        return 200

    monkeypatch.setattr(replit_scheduled_job, "_invoke", fake_invoke)

    replit_scheduled_job.run_job("alerts")

    assert calls == ["alerts"]


def test_invalid_boolean_control_fails_closed(monkeypatch):
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: "token",
    )
    monkeypatch.setenv("SKIP_AI", "sometimes")

    try:
        replit_scheduled_job.run_job("ingestion")
    except RuntimeError as error:
        assert str(error) == "SKIP_AI must be true or false"
    else:
        raise AssertionError("invalid controls must not silently use a default")