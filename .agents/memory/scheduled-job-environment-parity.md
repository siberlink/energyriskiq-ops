---
name: Scheduled-job environment parity
description: Environment requirements when moving protected API jobs into direct scheduled processes.
---

Direct scheduled runners must explicitly receive every feature flag, data-source
selector, and provider credential alias that the production API process relies
on.

**Why:** A daily index runner had database and core credentials but still failed
because index modules defaulted off outside the API process. After enabling
them, computations worked but interpretation modules degraded because they used
integration-specific OpenAI variable names rather than the standard alias.

**How to apply:** Compare the direct runner environment with the deployed API
environment before cutover. Set required feature flags and real-data selectors
explicitly, map compatible credential aliases, and add preflight checks for
mandatory data sources. Verify stage output, not only the shell exit status.

Scheduled capture jobs must also validate nested per-source results and must
never delete the last known valid market data before a replacement has been
fetched and stored transactionally.

**Why:** A closed-market capture returned no primary-provider data, lacked its
fallback credential, erased the previous session, and still exited successfully
because only the wrapper status was checked.

**How to apply:** Propagate required-source failures to a non-zero process exit,
and make replacement-plus-retention cleanup one transaction ordered so failed
fetches or writes preserve the prior valid observation.