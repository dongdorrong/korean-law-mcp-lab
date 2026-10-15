# Repo-local work and deferred gates

2026-10-15 작업 범위·검증은 `docs/completion-ledger.md`를 참조하십시오. Offline exporter, pinned upstream 준비, 논리 ID와 dry-run migration, 날짜/검증 상태, manifest checksum, synthetic reconciliation은 구현되었습니다. Live API 호출과 중앙 import는 실행하지 않았습니다.

남은 gate:
- 중앙 Knowledge v1 source_id enum에 법령 source를 등록할지 중앙 소유자 결정 및 새 schema 계약 검증.
- `legalize-kr` 라이선스/재배포 범위와 과거 pinned commit 가용성 검증.
- LAW_OC 사용 승인 뒤 인증·rate-limit·timeout·응답 schema·live 최신성 비교를 별도 실행.
- 중앙 답변 guard, 지원 adapter 승격, sparse 법령 분야 확장, 과거 개정 전체 이력 export는 별도 제품 범위.
- 새 CI runner/과금 승인 전에는 `scripts/verify.sh`만 로컬 실행. 비활성 초안: `docs/ci-workflow-draft.md`.

검증: `./scripts/verify.sh` (실데이터/키/네트워크 불필요).
