# Offline Knowledge pre-integration contract

`fordongdorrong` Knowledge v1 schema, commit `288246aa927dfec73db01679596b76bd2f8e4948`, SHA-256 `c0faecbdfce828f9697f1a35bc22df592aa35f60ea8381ee28df0d2825da12af`을 읽기 전용으로 확인했습니다. 이 schema의 `source_id` enum은 velog, thing, onenote, github-stars뿐입니다. 따라서 현재 법령 export는 **중앙 import 호환 완료가 아닙니다**. 중앙 코드/DB는 수정하지 않았으며 `scripts/reconcile_knowledge_contract.py`가 이 차이를 offline으로 보고합니다.

JSONL 필드: source_id, document_id, title, body, uri, content_hash, created_at, updated_at, visibility, lifecycle, deleted_at, indexable, metadata. `created_at`은 유효한 공포일이 있을 때만 채우고, `updated_at`은 export 관측 시각입니다. 법적 시행일은 `metadata.enforcement_date`에 별도로 둡니다. 누락·잘못된 법적 날짜는 null입니다. `temporal_relation=future_enforcement_date`는 단순 날짜 비교이지 법적 효력 판정이 아닙니다. `legal_effect_status=not_determined`를 유지합니다. 각 문서는 `metadata.evidence_kind=snapshot`, `verification_status=unverified`, `live_verified_at=null`, `legal_advice=false`입니다. 출처 경로·upstream commit·citation 필드를 포함하지만 공식 최신 원문 대조 완료를 뜻하지 않습니다.

SQLite documents는 JSONL의 metadata를 `metadata_json`에 보존합니다. FTS5 availability는 manifest에 기록합니다. manifest `generation`에는 JSONL/SQLite checksum과 `complete_snapshot`이 있습니다. 고정 경로 소비자는 **manifest 검증 후** 읽어야 합니다. 파일 단위 교체는 다중 파일 원자 트랜잭션이 아닙니다. 중간 중단 시 checksum 불일치를 거절해야 합니다. `--limit` export는 partial smoke이며 전체 snapshot으로 수입하면 안 됩니다.

새 ID는 법령ID가 있으면 법령ID/구분을 사용하고, 없으면 경로 fallback(weak)을 사용합니다. section 및 조문 번호는 ordinal과 분리합니다. 동일 자료의 content hash는 revision이고 Git commit은 provenance입니다. 미명시 부칙/별표의 위치 기반 구분은 개정 삽입 시 수동 mapping 검토가 필요합니다. `--migration-report`는 기존 ordinal ID를 실제 DB에 적용하지 않습니다.

Live MCP API 키 존재, upstream build, health, 인증 성공, 실제 법령 조회 성공은 별도 상태입니다. exporter는 live 호출을 하지 않으며 live_verified를 주장하지 않습니다. LAW_OC 발급·실호출·rate-limit/timeout/schema 검증과 지원 adapter 승격은 별도 gate입니다. 법률 자문 또는 자동 법적 유효성 판정은 범위 밖입니다.
