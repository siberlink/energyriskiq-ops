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