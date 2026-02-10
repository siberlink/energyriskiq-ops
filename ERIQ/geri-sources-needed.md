# GERI Sources Needed — Professional Assessment

## Overall Assessment

The ingestion pipeline is:

- Strong institutional core
- Excellent early-stage design
- Scientifically promising

But:

- It is Europe-centric
- It is underpowered in geopolitical security intelligence
- It is missing demand shock coverage
- It is missing OPEC / producer intelligence
- It is missing chokepoint monitoring

Those five gaps are very real GERI weaknesses.

---

## What Is Working Very Well

Most early risk platforms completely fail here — EnergyRiskIQ didn't.

### Reuters + EIA + ICIS

This is extremely strong. Those three alone give:

- Market legitimacy
- Primary data credibility
- Professional-grade signals

That is not trivial.

### FreightWaves Inclusion

This is actually very advanced thinking. Transit and logistics signals are massively underused in risk indices. Huge positive.

### EU Commission Feeds

Excellent for regulatory intelligence.

### Thematic Keyword Classification

For early stage — totally acceptable.

---

## Where GERI Is Currently Blind

### Blind Spot 1 — Middle East Military & Security Intelligence

This is the largest risk gap.

Middle East conflicts drive:
- Brent shocks
- Freight shocks
- LNG volatility
- Insurance spikes

Right now the system is mostly relying on Al Jazeera (very noisy). That is NOT sufficient.

### Blind Spot 2 — China Demand Intelligence

China is arguably the largest hidden energy risk driver globally.

Currently: zero China-specific ingestion.

This is very significant. China often leads:
- LNG pricing cycles
- Oil demand cycles
- Industrial energy consumption shocks

### Blind Spot 3 — OPEC & Producer Intelligence

Surprisingly missing. For an energy risk index this is critical.

### Blind Spot 4 — Maritime Security Monitoring

FreightWaves is present but NOT:
- Red Sea shipping threat intelligence
- Naval security signals
- Insurance risk signals

### Blind Spot 5 — Russia / Ukraine Infrastructure Monitoring

Relying indirectly on general sources is dangerous because Ukraine pipeline events historically caused TTF spikes.

---

## Exact Sources to Add

### Phase 1 — Must Add (Highest ROI)

#### OPEC Official Feed

- **Category:** Production policy
- **Why critical:** OPEC decisions are core energy price drivers
- **Add:** OPEC News RSS, OPEC press releases

#### ACLED (Armed Conflict Location & Event Data)

- **Category:** Conflict intelligence
- **Why:** Professional conflict event dataset used by governments
- **Covers:** Attacks, military escalation, infrastructure strikes
- **Signal value:** Huge

#### US State Department / OFAC Sanctions Releases

- **Category:** Sanctions intelligence
- **Why:** Sanctions drive massive supply disruptions

#### Lloyd's List OR Maritime Executive

- **Category:** Maritime security & shipping risk
- **Tracks:** Shipping attacks, insurance disruptions, Red Sea / Strait security
- **Value:** Extremely high

#### China Energy / Industrial Monitoring

- **Suggested sources:**
  - Caixin Energy (excellent Chinese macro energy reporting)
  - Xinhua energy sections
  - Platts Asia LNG coverage
- **Why:** China demand is a missing pillar in GERI

---

### Phase 2 — Very Strong Second Tier

#### Norwegian Petroleum Directorate

Norway is Europe's gas backbone.

#### QatarEnergy Press Releases

Major LNG supplier.

#### IEA News Releases

World energy system intelligence.

#### US DOE / LNG Export Monitoring

Very high value for TTF correlation.

---

### Phase 3 — Third Tier (Adds Depth)

#### Turkish Energy Ministry

Pipeline hub intelligence.

#### Suez Canal Authority

Transit chokepoint monitoring.

#### Panama Canal Authority

Shipping bottleneck intelligence.

#### India LNG Demand Monitoring

Emerging demand driver.

---

## Sources to Avoid Adding

More feeds does not equal better GERI. Avoid:

- General global news feeds
- Opinion-heavy energy blogs
- Financial aggregator spam feeds
- Twitter / social scraping (for now)

These create:
- Noise inflation
- False risk spikes

---

## Ideal Total Feed Count

Target: **25–30 high quality feeds**

Beyond that, signal quality decreases.

---

## Ideal Signal Balance Model

| Signal Domain | Target Coverage |
|---|---|
| Supply | 25% |
| Transit | 20% |
| Geopolitics | 20% |
| Demand | 15% |
| Policy | 15% |
| Infrastructure | 5% |

Current state:
- Overweight policy + EU news
- Underweight conflict + transit + demand

---

## Classifier Upgrade (Critical Next Step)

ML is not needed immediately. But these are required:

- **Named Entity Recognition** — identify specific actors, companies, infrastructure
- **Semantic clustering** — group related events beyond title matching
- **Temporal event detection** — distinguish developing vs. resolved events

These dramatically improve signal quality.

---

## Priority Expansion Roadmap

### Phase 1 — Immediate

Add:
1. OPEC
2. ACLED
3. Maritime Executive / Lloyd's
4. China energy demand source
5. OFAC sanctions

### Phase 2 — Next

Add:
6. Norway Petroleum Directorate
7. QatarEnergy
8. IEA
9. Suez Canal Authority

### Phase 3 — Later

Add:
10. Turkey pipeline intelligence
11. Panama Canal
12. India LNG demand monitoring

---

## The Big Strategic Insight

The biggest GERI weakness right now is:

- **Security intelligence**
- **Demand intelligence**
- **Chokepoint intelligence**

Not market news. Market news is already covered very well.

---

## Professional Verdict

If these steps are taken:

- Add 8–10 targeted high-impact sources
- Improve deduplication
- Add entity detection

GERI signal quality would likely improve dramatically.

The platform is much closer to institutional quality than most startups at this stage.

---

## Sources Added (Implementation Log)

The following 10 sources have been added to `src/config/feeds.json`, bringing the total from 14 to 24 feeds:

| # | Source | Feed URL | Weight | Blind Spot Addressed |
|---|---|---|---|---|
| 1 | **OPEC News** | `opec.org/opec_web/en/news.rss` | 1.0 | OPEC & Producer Intelligence |
| 2 | **OPEC Press Releases** | `opec.org/opec_web/en/pressreleases.rss` | 0.95 | OPEC & Producer Intelligence |
| 3 | **Maritime Executive** | `maritime-executive.com/articles.rss` | 0.9 | Maritime Security / Chokepoints |
| 4 | **Hellenic Shipping — Oil & Energy** | `hellenicshippingnews.com/category/oil-energy/feed/` | 0.85 | Maritime / Tanker / LNG Shipping |
| 5 | **Norwegian Offshore Directorate** | `sodir.no/en/whats-new/news/rss/` | 0.9 | European Gas Supply (Norway) |
| 6 | **Rigzone** | `rigzone.com/news/rss/rigzone_latest.aspx` | 0.8 | Upstream / Drilling / Infrastructure |
| 7 | **Xinhua — Business/Energy** | `xinhuanet.com/english/rss/chinaview/business.xml` | 0.85 | China Demand Intelligence |
| 8 | **China Daily — Business** | `chinadaily.com.cn/rss/business_rss.xml` | 0.8 | China Demand Intelligence |
| 9 | **Hellenic Shipping — Shipping** | `hellenicshippingnews.com/category/shipping-news/feed/` | 0.8 | Transit / Chokepoint / Red Sea |
| 10 | **OPEC Press Releases** (dual coverage) | — | — | Production policy decisions |

### Blind Spots Now Covered

- **OPEC & Producer Intelligence** — Fully addressed (2 official OPEC feeds)
- **Maritime Security / Chokepoints** — Addressed (Maritime Executive + 2 Hellenic feeds)
- **China Demand Intelligence** — Addressed (Xinhua + China Daily)
- **European Gas Supply** — Strengthened (Norwegian Offshore Directorate)
- **Upstream Infrastructure** — Added (Rigzone)

### Remaining Gaps for Future Phases

- **ACLED conflict data** — Requires API integration, not RSS
- **OFAC sanctions** — RSS feed retired Jan 2025; requires web scraping or email parsing
- **QatarEnergy press releases** — No public RSS feed available
- **IEA news** — No official RSS feed; would need third-party generator
- **Suez/Panama Canal authorities** — No RSS feeds; require custom monitoring
- **India LNG demand** — No dedicated English RSS source identified
