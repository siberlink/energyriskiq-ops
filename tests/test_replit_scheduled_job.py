from scripts import replit_scheduled_job


def test_alerts_run_once_before_deliveries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: ("https://example.test", "token"),
    )

    def fake_run_one(_app_url, _token, name, _job):
        calls.append(name)
        return 200

    monkeypatch.setattr(replit_scheduled_job, "_run_one", fake_run_one)

    replit_scheduled_job.run_job("alerts")

    assert calls == ["alerts", "pro_delivery", "trader_delivery"]


def test_busy_alerts_do_not_launch_deliveries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: ("https://example.test", "token"),
    )

    def fake_run_one(_app_url, _token, name, _job):
        calls.append(name)
        return 409

    monkeypatch.setattr(replit_scheduled_job, "_run_one", fake_run_one)

    replit_scheduled_job.run_job("alerts")

    assert calls == ["alerts"]


def test_named_job_uses_expected_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(
        replit_scheduled_job,
        "_configuration",
        lambda: ("https://example.test", "token"),
    )

    def fake_run_one(_app_url, _token, name, job):
        calls.append((name, job.path))
        return 200

    monkeypatch.setattr(replit_scheduled_job, "_run_one", fake_run_one)

    replit_scheduled_job.run_job("intraday")

    assert calls == [
        ("intraday", "/internal/run/intraday-price-capture"),
    ]