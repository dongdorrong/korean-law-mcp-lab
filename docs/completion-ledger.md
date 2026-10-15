# Repo-local completion ledger (2026-10-15)

Base: `8645d825f5b99349fedef12449772eb7e5bf70de`. Baseline: 3 offline tests passed. This is a lab/evidence exporter, not legal advice or current-law validation.

| ID/source | Classification | Evidence / change | Acceptance / status |
| --- | --- | --- | --- |
| LAW-01; Issue #1 provenance | AUTO_REQUIRED | `upstreams.lock.json`, pinned bootstrap and proposal-only update; current lock sourced from prior manifest | Offline lock/dirty-check tests pass; both old SHAs fetched in isolated shallow checkout; legalize-kr license remains unverified |
| LAW-02; Issue #1 identity | AUTO_REQUIRED | law ID/path fallback + section/article identity, content revision, dry-run old→new report | insertion/repeated supplemental citation/duplicate identity regression passes; no central migration run |
| LAW-03; Issue #1 freshness | AUTO_REQUIRED | separate law dates and observed-at; snapshot always unverified, live_verified_at null | invalid/future-date and conflicting identity fixture passes; no legal-effect claim; live comparison not authorized |
| LAW-04; TODO export quality | AUTO_REQUIRED | zero/duplicate/partial rejection; staged artifacts, manifest-last checksums and consumer validator | synthetic checksum/empty/limit/symlink/interrupted publish tests pass; old fixed-path readers must adopt validator |
| LAW-05; TODO article/annex/citation | AUTO_REQUIRED | preamble/section kept, citation fields, legal_advice=false, offline reconciliation | synthetic export tests pass; central source_id enum currently rejects this source |
| TODO importer contract; Issue #1 | OUT_OF_SCOPE | pinned central v1 fixture and local dry-run reveal source_id not registered | central repository must own registration; no central write |
| TODO answer guard; Issue #1 | OUT_OF_SCOPE | contract metadata recommends citations; no central answer pipeline changed | deferred integration |
| TODO live LAW_OC smoke; Issue #1 | OWNER_DECISION | no credential use, auth call, or health inference | not run |
| TODO live/local merge strategy | OUT_OF_SCOPE | local-only remains default; no supported adapter | deferred integration |
| TODO sparse expansion | OWNER_DECISION | existing three-law sparse set locked; no new domains | not expanded |
| TODO amendment history docs | AUTO_OPTIONAL | current article revisions via hash; historical corpus export not necessary for evidence snapshot | not adopted |
| Issue #1 supported promotion | OWNER_DECISION | lab remains read-only and unpromoted | deferred unchanged |

Outstanding technical gates: upstream legalize-kr license is unverified; pinned old commits were fetched but not used as test data; central source registration is incompatible; live/auth/rate-limit/timeout/schema behavior is unverified because this exporter has no live client and live API use was not authorized. These are not test passes. Fixed-path legacy consumers that do not call the checksum validator are not safe during interrupted publication; central import stays disabled.
