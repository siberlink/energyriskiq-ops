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