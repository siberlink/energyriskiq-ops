---
name: Forecast release gating
description: Statistical evidence required before presenting price-risk forecasts as a validated edge.
---

Price-risk models must remain visibly research-only unless purged walk-forward
tests beat a causal, fold-local baseline for every displayed target on both
directional accuracy and probability calibration.

**Why:** A model can appear directionally useful while its probabilities are
worse than a historical base-rate forecast, and overlapping outcome windows
can leak future information into validation.

**How to apply:** Use only features available at the forecast timestamp, purge
the maximum target horizon between train and test folds, require adequate test
observations per target, compare accuracy and Brier score against baselines
derived only from each fold's training history, and keep warnings prominent
until every production-facing target passes.