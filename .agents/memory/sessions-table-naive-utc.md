---
name: sessions table naive-UTC convention
description: How session expiry is stored/compared so new code doesn't silently treat sessions as expired/valid wrong.
---

# sessions.expires_at is naive UTC

`sessions.expires_at` and `created_at` are `timestamp WITHOUT time zone`, and the
app writes them with Python `datetime.utcnow()` (naive UTC). `verify_user_session`
compares against `datetime.utcnow()` in Python.

**Rule:** When checking session validity in SQL, compare against
`(NOW() AT TIME ZONE 'UTC')`, NOT `NOW()`.

**Why:** `NOW()` returns `timestamptz`; comparing it to a naive UTC `timestamp`
makes Postgres interpret the naive value in the server session timezone. If that
timezone is not UTC, live sessions can be judged expired (or vice-versa).
`(NOW() AT TIME ZONE 'UTC')` yields current UTC as a naive timestamp that matches
the stored convention.

**How to apply:** Any new feature that joins/filters on `sessions` (e.g. token →
user_id resolution for beacons/analytics) must use the `AT TIME ZONE 'UTC'` form.
