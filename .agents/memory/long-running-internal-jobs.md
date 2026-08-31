---
name: Long-running internal jobs
description: Constraints for ingestion and other protected jobs that run longer than public proxy and database idle-session limits.
---

Do not run lengthy ingestion or daily pipelines as synchronous requests through
the public Cloudflare-fronted application URL. Use a direct scheduled process,
or return quickly and track durable background-job status.

**Why:** Cloudflare returns HTTP 524 after waiting roughly 100 seconds even
while the API process continues working, so the caller reports failure and may
retry work that is still active.

**How to apply:** Scheduled artifacts should invoke protected handlers directly
instead of calling the public URL. Any HTTP trigger for long work must use an
asynchronous start-and-poll contract rather than waiting for completion.

Treat a long-held PostgreSQL advisory lock as unsafe if its dedicated connection
is idle while application work runs. A database proxy or network can close that
session, implicitly releasing the lock before the work finishes.

**Why:** A lengthy ingestion run logged an unexpected SSL connection closure
when releasing its advisory lock, while a retry appeared to overlap the first
execution.

**How to apply:** Every outer and nested lock held during long work needs a
keepalive heartbeat; protecting only the orchestration lock is insufficient.
Treat heartbeat loss as a job failure.

Apply send-rate limits when rows are claimed, not after a larger batch has been
changed from `queued` to `sending`.

**Why:** Claiming more rows than the per-run circuit breaker left untouched rows
stranded in `sending`, where later workers could not retry them.

**How to apply:** Use the smaller of the batch limit and run limit in the
locking query. Recovery may requeue only rows with no provider ID, sent
timestamp, or error; stale alerts should be explicitly skipped rather than sent.