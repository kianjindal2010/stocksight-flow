# StockSight legacy-data migration function

Run with body `dry-run` first. It reports legacy rows that match Appwrite users by email.
After the expected users have signed in with Google, run again with body `apply`.

The function reads from `default/users` and writes the rebuilt StockSight state to
`6a840e69001dca03b9d4/learner_staate`. It never deletes the legacy rows.
