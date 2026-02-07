# Ranked Global Source Database (Top 50 Energy-Risk Feeds)

## Tier 0 — Primary / Institutional (best signal, lowest noise)

1. Reuters Energy (market-moving; RSS may be restricted)
2. EIA (US Energy Information Administration) — RSS feeds hub
3. US DOE (Energy News / Fossil Energy & Carbon Mgmt RSS)
4. IEA (International Energy Agency) — news/press releases (no official RSS found; use page-to-feed tooling if needed)
5. OPEC (Press releases page) (official page; if you need RSS, generate from page)
6. European Commission — Energy (already integrated)
7. International Maritime Organization (IMO) — RSS feeds (Press briefings, etc.)
8. IRENA — RSS feeds (energy transition; useful for structural risk layer)
9. ACLED (conflict events data + API; not RSS, but high value)
10. Norwegian Offshore Directorate (SODIR) — RSS feeds

## Tier 1 — Market / Commodity / Gas-LNG Intelligence (high signal)

11. ICIS (verify you're not using podcast-only feed; swap to article feed if possible)
12. S&P Global Commodity Insights / Platts (oil/LNG) (often paywalled; use headlines feed if available)
13. Argus Media (paywalled; headlines feed if available)
14. Energy Intelligence (already integrated; has RSS)
15. Oil & Gas Journal (already integrated)
16. Rystad / WoodMac public insights (often newsletters; use RSS if available)
17. Baker Hughes rig count / macro drilling indicators (can be RSS/updates)

## Tier 2 — Maritime / Transit / Chokepoints (critical for "systemic" energy risk)

18. The Maritime Executive (already integrated)
19. Lloyd's List (RSS feeds exist; may require subscription/login)
20. MarineLink / Maritime Reporter — RSS feeds
21. International Chamber of Shipping (ICS) updates (security guidance; often non-RSS)
22. Suez Canal Authority updates (often non-RSS; page monitoring)
23. Panama Canal Authority advisories (often non-RSS; page monitoring)
24. NATO / EU maritime security releases (limited, but high-impact)

## Tier 3 — Conflict / Security / Sanctions (high value when filtered)

25. UN Security Council / Maritime Security reporting (context + escalations)
26. US State Department RSS feeds (sanctions/diplomacy drivers)
27. OFAC "Recent Actions" page (RSS retired; use email/subscription + page monitoring)
28. UK OFSI sanctions updates (UK side of sanctions intelligence)
29. EU sanctions updates (Council / EEAS)
30. DefenseIQ Naval/Maritime security RSS (use carefully; niche but relevant)

## Tier 4 — Region-Specific "Must Cover" (fill current Europe bias)

### Middle East / GCC
31. QatarEnergy press releases
32. Saudi Aramco news / pricing announcements (if accessible)
33. UAE energy ministry / ADNOC news
34. Iraq oil ministry updates
35. Iran-related sanctions + shipping advisories (via OFAC/State + maritime sources)

### Russia / Black Sea / Caspian
36. Ukraine energy ministry / infrastructure statements
37. Turkey energy ministry / BOTAŞ updates
38. Caspian pipeline / Kazakhstan energy ministry

### Asia-Pacific (Demand shock engine)
39. China NDRC energy policy updates
40. China customs/LNG import notes (where accessible)
41. India MoPNG (petroleum & natural gas) updates
42. Japan METI energy updates
43. Korea energy ministry / KOGAS updates

### Africa / LatAm (supply disruptions + LNG)
44. Nigeria NNPC / LNG updates
45. Algeria Sonatrach updates
46. Libya NOC statements
47. Venezuela PDVSA / sanctions updates
48. Brazil Petrobras / ANP updates

## Tier 5 — Curated Secondary (only if classifier/dedup is strong)

49. Financial Times energy (paywalled; headlines only)
50. WSJ energy (paywalled; headlines only)

---

**Note:** Some items above are not pure RSS (official sites often moved to email). Ingestion can be RSS + page monitors + email-to-parser + datasets (ACLED). The key is signal quality, not RSS purity.
