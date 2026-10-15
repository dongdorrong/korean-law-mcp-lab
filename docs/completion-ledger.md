# Repo-local completion ledger — 2026-10-15

Baseline commit `8645d825f5b99349fedef12449772eb7e5bf70de`; baseline offline suite: 3 pass. `AUTO_REQUIRED` means required repo-local implementation, **not** live/central promotion. All paths below are repository-relative. This ledger is a per-item implementation record; it does not approve legal accuracy or central import. Synthetic tests only.

| ID / source | Requirement | Current evidence at baseline | Classification | Intended change / final artifact | Test or acceptance | Status / blocker or decision |
| --- | --- | --- | --- | --- | --- | --- |
| LAW-01a / bootstrap | Reproduce immutable upstream | `bootstrap-upstreams.sh` pulled main | AUTO_REQUIRED | `upstreams.lock.json`, pinned `scripts/upstreams.py` | isolated shallow fetch at both locked SHA; dirty/remote/sparse tests | IMPLEMENTED; license gate E1 |
| LAW-01b / Issue #1 | Candidate update separate | main pull mixed update/prepare | AUTO_REQUIRED | `--propose-update`, no checkout mutation | candidate command read-only | IMPLEMENTED; candidate approval E1 |
| LAW-01c / Issue #1 | License/provenance | old manifest had commit but no lock/license | EVIDENCE_BLOCKED | lock records provenance and unverified license | legalize-kr license review required | E1; no redistribution claim |
| LAW-02a / exporter | Stable logical identity | ordinal in document ID | AUTO_REQUIRED | law ID/path fallback + section + article; revision hash | insertion/reorder/repeated appendix fixture | IMPLEMENTED; weak fallback documented |
| LAW-02b / exporter | Prior ID dry-run migration | no mapping | AUTO_REQUIRED | `migration_report` requires prior JSONL | insertion fixture maps actual old `#제2조-0002`; ambiguous unresolved | IMPLEMENTED; real DB migration D1 |
| LAW-02c / Issue #1 | Unlabeled supplemental identity | no separate section | AUTO_REQUIRED | content-fingerprint weak identity; no false stable claim | unlabeled reorder fixture | IMPLEMENTED with weak identity; amendment mapping D1 |
| LAW-03a / exporter | Separate dates | enforcement misused as updated_at | AUTO_REQUIRED | created/updated, promulgation/enforcement/source-modified/observed/live fields | invalid/future/modified fixture | IMPLEMENTED; source-modified unknown unless provided |
| LAW-03b / Issue #1 | Snapshot/live freshness | snapshot labeled official text | AUTO_REQUIRED | unverified snapshot, no live_verified; explicit policy classifier | stale/conflict/unknown offline fixture | IMPLEMENTED; live validation D2 |
| LAW-03c / Issue #1 | Repeal/amendment semantics | raw status only | AUTO_REQUIRED | raw status retained, legal_effect_status=not_determined; lifecycle separate | synthetic repeal fixture | IMPLEMENTED for non-claim; actual legal effect E2 |
| LAW-04a / exporter | Missing/empty/invalid/duplicate/limit | empty could overwrite existing | AUTO_REQUIRED | fail closed, explicit allow-empty, partial status | empty/malformed/duplicate/limit tests | IMPLEMENTED |
| LAW-04b / exporter | Publish generations | JSONL write and SQLite delete separate | AUTO_REQUIRED | staged validation; validated complete fixed baseline frozen; immutable subsequent generation + single pointer; journal dry-run recovery | failure at each first-publish boundary, baseline parity, pointer read/race fixtures | IMPLEMENTED; legacy remains on prior complete generation |
| LAW-04c / exporter | Path/FTS/checksum safety | no checksum/FTS capability | AUTO_REQUIRED | symlink/alias/root checks, manifest hashes, FTS flag | CLI symlink, alias, checksum, FTS tests | IMPLEMENTED; no whole-set atomic claim |
| LAW-05a / TODO #6 | Article, annex, frontmatter | article-only regex, last article swallowed annex | AUTO_REQUIRED | section-specific nonarticle chunks, strict frontmatter/CRLF | two annexes, malformed YAML fixtures | IMPLEMENTED |
| LAW-05b / Issue #1 | Citation and legal-advice metadata | partial fields, misleading verification | AUTO_REQUIRED | source/citation/section metadata, legal_advice=false | JSONL/SQLite parity tests | IMPLEMENTED; not legal advice |
| LAW-05c / TODO #1 | Central Knowledge contract | unknown central source enum | AUTO_REQUIRED | pinned full schema + offline reconcile | invalid schema test; source_id rejection observed | IMPLEMENTED dry-run; central registration D3 |
| LAW-05d / Issue #1 | Fake live failure boundary | no mockable boundary | AUTO_REQUIRED | `scripts/live_contract.py`, pinned `searchLaw` XML interface fixture; no network transport | fake 401/403/429/timeout/XML schema/transport | IMPLEMENTED offline; actual calls D2 |
| TODO #1a | JSONL ingest existence | docs assumed importer | OUT_OF_SCOPE | central schema read only; no import | dry-run reports incompatible | D3 central owner |
| TODO #1b | SQLite documents importer | docs assumed importer | OUT_OF_SCOPE | local SQLite parity only | synthetic DB parity | D3 central owner |
| TODO #1c | RAG metadata filter | docs recommended fields | OUT_OF_SCOPE | citation fields retained; no central filter change | source metadata tests | D3 central owner |
| TODO #2 / Issue #1 | Central answer guard | not present here | OUT_OF_SCOPE | metadata `legal_advice=false`, must-cite manifest | synthetic export | D3 central owner |
| TODO #3 / Issue #1 | LAW_OC key/live smoke | not validated | OWNER_DECISION | no key or live request | offline fake tests do not count as live | D2 |
| TODO #4 | Local/live merge strategy | candidate prose only | OWNER_DECISION | local-only default; no supported adapter | no live calls | D2/D3 |
| TODO #5 | More sparse law domains | three domains selected | OWNER_DECISION | unchanged lock scope | pinned sparse check | D4 scope expansion |
| TODO #6 historical revisions | no full amendment corpus | AUTO_OPTIONAL | content revision per snapshot only | no historical corpus claim | not adopted; major scope |
| Issue #1 promotion | Supported adapter | lab/deferred | OWNER_DECISION | no promotion/central write | manifest unverified state | D3; deferred unchanged |
| Common CI | Test-only CI | no workflow/runner approval | OWNER_DECISION | `scripts/verify.sh`, inactive `docs/ci-workflow-draft.md` | local 3.11/3.12 suite | D5; active CI not enabled |

**Decisions/gates:** D1 real existing ID/data migration; D2 LAW_OC credentials and live validation; D3 central Knowledge registration, guard and supported adapter; D4 new legal domains; D5 CI runner/billing. **Evidence blockers:** E1 legalize-kr license/redistribution review; E2 official latestness/real legal validity. The pinned commits are independently fetchable, but were not used as test data. Existing tracked `exports/` are legacy artifacts and were not changed. No external account, legal API, central repository, existing database or original checkout was written.
