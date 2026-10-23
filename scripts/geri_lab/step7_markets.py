"""Same lab market source/shape, current completed sessions only."""
from datetime import datetime, timedelta
from .data import readonly_snapshot, completed_market_end


def markets(start):
    result={}
    with readonly_snapshot() as c:
        for name,table,column in (("Brent","oil_price_snapshots","brent_price"),
                                  ("TTF","ttf_gas_snapshots","ttf_price")):
            c.execute(f"""SELECT date,{column} AS value FROM {table}
                WHERE date BETWEEN %s AND %s AND {column}>0
                ORDER BY date,id""",
                      (start-timedelta(days=60),datetime.utcnow().date()-timedelta(days=1)))
            result[name]=[dict(r) for r in c.fetchall()]
    return result
