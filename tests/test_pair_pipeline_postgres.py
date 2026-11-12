"""Daily orchestration + real SQL/audit; remote website HTTP and sends mocked."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
import requests

from tests.disposable_postgres import disposable_pg, sql_cursor


@pytest.mark.parametrize("unavailable", [False, True])
def test_real_sql_pair_precedes_report_and_audits_actual_dates(disposable_pg, monkeypatch, unavailable):
    from src.api import internal_routes as routes
    from src.reri import website_trigger as trigger
    from src.delivery.pro_delivery_worker import record_index_delivery
    from src.delivery.index_dates import index_observations
    from psycopg2.extensions import make_dsn
    monkeypatch.setenv("DATABASE_URL", make_dsn(**disposable_pg))
    monkeypatch.setenv("PRODUCTION_DATABASE_URL", make_dsn(**disposable_pg))
    monkeypatch.setenv("WEBSITE_BASE_URL", "https://website.invalid")
    monkeypatch.setenv("INTERNAL_RUNNER_TOKEN", "offline")
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    old = day - timedelta(days=1)
    with sql_cursor(disposable_pg) as c:
        c.execute("""
            DROP TABLE IF EXISTS pair_observations,user_alert_deliveries;
            CREATE TABLE pair_observations(name TEXT,day DATE,value NUMERIC,
                stored_at TIMESTAMP DEFAULT now(),PRIMARY KEY(name,day));
            CREATE TABLE user_alert_deliveries(user_id INT,channel TEXT,status TEXT,
                delivery_kind TEXT,created_at TIMESTAMP,sent_at TIMESTAMP,
                geri_date DATE,last_error TEXT);
            CREATE UNIQUE INDEX ON user_alert_deliveries(user_id,channel,geri_date)
                WHERE delivery_kind='index_digest' AND geri_date IS NOT NULL;
        """)
        c.execute("INSERT INTO pair_observations(name,day,value) VALUES('eeri',%s,50),('egsi_m',%s,21.13)",
                  (old, old))
    def remote(*args, **kwargs):
        if unavailable:
            raise requests.Timeout("mocked remote website unavailable")
        assert kwargs["headers"]["X-Runner-Token"] == "offline"
        with sql_cursor(disposable_pg) as c:
            for name, value in (("eeri", 51), ("egsi_m", 18.24)):
                c.execute("INSERT INTO pair_observations(name,day,value) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                          (name, day, value))
        return SimpleNamespace(status_code=200, json=lambda: {
            "success": True, "stages": {
                "eeri": {"date": str(day), "value": 51, "status": "stored",
                         "model_version": "eeri_ttf_v3"},
                "egsi_m": {"date": str(day), "value": 18.24, "status": "stored"}}})
    monkeypatch.setattr(trigger.requests, "post", remote)
    monkeypatch.setattr(routes, "validate_runner_token", lambda _: None)
    monkeypatch.setattr(routes, "run_job_with_lock",
                        lambda name, fn: ({"status": "ok", "details": fn()}, 200))
    monkeypatch.setattr(routes.time, "sleep", lambda _: None)
    for name in ("market_data_capture", "oil_price_capture", "gas_storage_capture",
                 "lng_price_capture", "egsi_s_compute"):
        monkeypatch.setattr(routes, "run_" + name, lambda **kw: {"status": "success"})
    def geri(**kw):
        with sql_cursor(disposable_pg) as c:
            c.execute("INSERT INTO pair_observations(name,day,value) VALUES('geri',%s,14) ON CONFLICT DO NOTHING", (day,))
        return {"status": "success", "value": 14}
    monkeypatch.setattr(routes, "run_geri_compute", geri)
    def observations():
        data = {}
        with sql_cursor(disposable_pg, commit=False) as c:
            for name in ("geri", "eeri", "egsi_m"):
                c.execute("SELECT day date,value FROM pair_observations WHERE name=%s ORDER BY day DESC LIMIT 1", (name,))
                data[name] = dict(c.fetchone())
        return index_observations(data["geri"], data["eeri"], data["egsi_m"])
    def report(**kw):
        actual = observations()
        assert actual["eeri"]["date"] == str(old if unavailable else day)
        return {"status": "success", "index_observations": actual}
    monkeypatch.setattr(routes, "run_daily_report", report)
    def delivery(**kw):
        record_index_delivery(1, "telegram", "sent", index_date=day, geri_value=14,
                              methodology="v1.2", index_observations=observations())
        return {"status": "success"}
    monkeypatch.setattr(routes, "run_pro_delivery", delivery)
    result = routes.run_daily_index_pipeline(True, "offline")["details"]
    assert (result["pipeline_status"] == "degraded") is unavailable
    assert result["daily_report"]["status"] == "success"
    assert result["delivery"]["status"] == "success"
    with sql_cursor(disposable_pg, commit=False) as c:
        c.execute("SELECT last_error FROM user_alert_deliveries")
        audit = json.loads(c.fetchone()["last_error"])
    assert audit["index_observations"]["egsi_m"]["date"] == str(old if unavailable else day)
    assert audit["index_observations"]["egsi_m"]["stale"] is unavailable
    assert audit["index_observations"]["geri"]["value"] == 14
