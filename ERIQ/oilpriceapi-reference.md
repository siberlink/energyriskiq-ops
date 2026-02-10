# OilPriceAPI.com Reference

## Overview

OilPriceAPI.com provides **global commodity/wholesale trading prices**, not regional retail prices.

## What They Offer

- **Global benchmark prices**: WTI (US), Brent (Europe/International), TTF Natural Gas, OPEC basket
- **50+ commodities** with real-time updates every 1-2 minutes
- **Commodity futures** (96 contract months with calendar spreads and contango/backwardation analysis)
- **Historical data** up to 1 year
- **2.8M+ monthly data points** with 99.98% uptime

## Key Features

| Feature | Details |
|---------|---------|
| Update Frequency | 1-2 minutes for major commodities |
| Uptime | 99.98% |
| API Type | REST API with JSON responses |
| SDKs | Python, JavaScript, Ruby |
| Authentication | Token-based |
| Webhooks | Available (for price threshold alerts) |

## What They Do NOT Offer

- Country-specific or regional retail gas station prices
- Local pump prices by region
- Per-country consumer fuel prices

## Usage in EnergyRiskIQ

For **EGSI-S** (Europe Gas Stress Index - System), we use OilPriceAPI for:
- **TTF Natural Gas prices** - The European wholesale natural gas benchmark (Title Transfer Facility)
- This is the main European gas hub price, appropriate for measuring European gas market stress
- It's a global-level trading price for the European market, not broken down by individual countries

Environment variable: `OIL_PRICE_API_KEY`

## Alternative APIs for Regional/Retail Prices

If regional retail gas prices are ever needed:
- **GlobalPetrolPrices.com** - 135 countries, weekly/monthly updates for retail fuel prices
- **EIA.gov** - US regional data and petroleum statistics

## API Documentation

- Official docs: https://docs.oilpriceapi.com/
- Signup: https://www.oilpriceapi.com/signup

## Quick Example

```bash
curl "https://api.oilpriceapi.com/v1/prices/latest?by_code=WTI_USD" \
  -H "Authorization: Token YOUR_API_KEY"
```

Response:
```json
{
  "status": "success",
  "data": {
    "price": 78.45,
    "change_24h": 1.05,
    "timestamp": "2025-01-03T15:30:00Z"
  }
}
```

---
*Last updated: February 2026*
