# Inactive CI draft

No active workflow is installed because an approved runner/billing path has not been established. A future test-only workflow should check out source with read-only permissions, no secrets, bounded timeout, run `scripts/verify.sh`, and never invoke live LAW_OC or write central data. This document does not trigger CI.
