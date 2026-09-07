from datetime import date

from src.ingest import intraday_prices


class _Cursor:
    def __init__(self, fail_insert=False):
        self.fail_insert = fail_insert
        self.statements = []

    def execute(self, statement, params):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, params))
        if self.fail_insert and normalized.startswith("INSERT INTO"):
            raise RuntimeError("insert failed")


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, *_args):
        return False


def test_failed_fetch_preserves_existing_rows(monkeypatch):
    writes = []
    monkeypatch.setattr(intraday_prices, "_fetch_via_yfinance", lambda _ticker: None)
    monkeypatch.setattr(intraday_prices, "_fetch_via_oilpriceapi", lambda _code: None)
    monkeypatch.setattr(
        intraday_prices,
        "_replace_hourly_price",
        lambda *args: writes.append(args),
    )

    result = intraday_prices.capture_intraday_prices()

    assert writes == []
    assert result["status"] == "failed"
    assert result["failed_assets"] == ["brent", "wti", "natgas"]


def test_valid_price_is_stored_before_old_rows_are_deleted(monkeypatch):
    cursor = _Cursor()
    monkeypatch.setattr(
        intraday_prices,
        "get_production_cursor",
        lambda commit: _CursorContext(cursor),
    )

    intraday_prices._replace_hourly_price(
        "intraday_brent",
        date(2026, 9, 7),
        6,
        96.28,
        1.2,
        1.3,
        "oilpriceapi",
    )

    assert cursor.statements[0][0].startswith("INSERT INTO intraday_brent")
    assert cursor.statements[1][0].startswith("DELETE FROM intraday_brent")


def test_failed_insert_never_attempts_cleanup(monkeypatch):
    cursor = _Cursor(fail_insert=True)
    monkeypatch.setattr(
        intraday_prices,
        "get_production_cursor",
        lambda commit: _CursorContext(cursor),
    )

    try:
        intraday_prices._replace_hourly_price(
            "intraday_brent",
            date(2026, 9, 7),
            6,
            96.28,
            None,
            None,
            "oilpriceapi",
        )
    except RuntimeError as error:
        assert str(error) == "insert failed"
    else:
        raise AssertionError("the simulated insert must fail")

    assert len(cursor.statements) == 1