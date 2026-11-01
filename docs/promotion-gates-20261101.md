# 법률 근거 어댑터 로컬 승격 조건 점검 — 2026-11-01

이슈 #1의 **오프라인 후보 계약**이다. 지원 어댑터 승격은 보류하고 owner 검토를 기다린다.
법률 자문·최신 법령·실제 효력을 검증한 결과가 아니다. 실제 LAW_OC 인증, 호출 한도,
timeout, 오류 및 응답 스키마는 모두 미검증이다. 합성 fixture가 이를 대신하지 않는다.

## 출처·버전·라이선스와 갱신

| upstream | 고정 버전 | 확인 근거와 남은 한계 |
| --- | --- | --- |
| [legalize-kr/legalize-kr](https://github.com/legalize-kr/legalize-kr) | `874b58594654505fdc409fd42c02d100d84d51ce` 데이터 스냅숏 | [고정 README](https://github.com/legalize-kr/legalize-kr/blob/874b58594654505fdc409fd42c02d100d84d51ce/README.md)는 법령 원문을 정부 공공저작물, 구조·메타데이터를 MIT라고 설명한다. [고정 루트 목록](https://api.github.com/repos/legalize-kr/legalize-kr/git/trees/874b58594654505fdc409fd42c02d100d84d51ce)은 `README.md`, `kr/`만 포함한다(`truncated=false`). 별도 LICENSE 파일은 확인되지 않았다. README 설명만으로 재배포 범위를 확정하지 않으며 E1 검토를 유지한다. 하위 전체 법령은 내려받거나 조사하지 않았다. |
| [chrisryugj/korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) | `f71b28c992db7b1347b7cfb68695c38392339ef0`, `4.1.1` | [실제 LICENSE](https://github.com/chrisryugj/korean-law-mcp/blob/f71b28c992db7b1347b7cfb68695c38392339ef0/LICENSE)의 MIT 본문·저작권 표기(2025 Chris)와 [package.json](https://github.com/chrisryugj/korean-law-mcp/blob/f71b28c992db7b1347b7cfb68695c38392339ef0/package.json)의 버전을 대조했다. 소프트웨어 라이선스 확인이며 법령 데이터·API 이용 조건까지 확인한 것은 아니다. |

2026-11-01에 고정 커밋의 공개 원문을 조회했다. `upstreams.lock.json`의 SHA와 기존
snapshot 출처 기록을 보존했다. `runtime.lock.json`은 별도로 해시가 잠긴 의존성 패치
실행 환경이며 upstream 원본과 섞지 않는다.

갱신은 다음 순서를 따른다. 이 점검에서는 갱신을 실행하지 않았다.

1. 별도 작업에서 `scripts/upstreams.py --propose-update`로 후보 SHA만 확인한다.
2. 후보 커밋의 README·LICENSE·데이터 출처·스키마 변경을 검토하고 owner가 범위를 결정한다.
   force-push가 발생해도 기존 lock을 자동 교체하거나 hard reset하지 않는다.
3. 승인한 SHA를 lock에 반영하고 격리된 새 checkout을 준비한다. 원본·기존 runtime을 덮어쓰지 않는다.
4. Python 3.11·3.12 전체 시험, 합성 내보내기, 명시적 중앙 스키마 대조와 ID migration dry-run을 수행한다.
5. 기존 고정 출력은 동결한다. 새 세대의 포인터 소비, 실제 데이터 이전·중앙 등록·지원 승격은 별도 검토한다.

## 종류와 시간 의미

`law_adapter/dry_run.py`의 `preview()`가 순수 메모리 계약을 구현한다. upstream 실행 환경이나
`scripts/live_contract.py`의 실험용 fake transport를 가져오지 않는다.

| 입력/결과 | 구조와 의미 |
| --- | --- |
| 내장/로컬 snapshot | `snapshot_documents` → `evidence_kind=snapshot`, `source.kind=local_snapshot`. exporter의 명시적 snapshot 표지가 있어야 한다. 고정 upstream 검증을 통과한 경우에만 exporter가 commit을 기록한다. |
| 사용자 제공 자료 | `user_documents` → `evidence_kind=user_provided`, `source.kind=user_supplied`. 자료가 스스로 주장한 live 검증·upstream commit은 승계하지 않는다. |
| 실시간 요청 | `requested_kind=live` → `status=live_validation_required`, `evidence=[]`, `live_verified=false`. snapshot/user 자료를 읽거나 대체하지 않는다. 실제 live 결과 수신·검증은 아직 구현하지 않았다. |
| 혼합 오프라인 조회 | `all_offline`은 두 종류의 표지를 각 근거에 그대로 보존한다. 실제 live를 섞지 않는다. |

모든 반환 근거에는 source reference, 인용(법령명·구분·조문·section·문서 ID·내용 hash),
관측 시각, 공포일, 시행일, 최신성 상태, 법률 자문 아님, 사람 검토 요구가 있다.
모르는 날짜는 null이며 다른 날짜나 현재 시각으로 채우지 않는다.
기존 동결 출력에 새 표지가 없으면 새 계약에 자동으로 맞춘 것처럼 취급하지 않는다.
인용의 `identity_strength`는 exporter의 식별자 강도 표지를 보존하며, 입력에 없으면 null이다.
이 표지는 동일성·출처 검증 성공을 뜻하지 않는다.

- `observed_at`: 해당 자료를 로컬에서 관측한 시각이다. exporter의 `updated_at`도 이 시각이다.
  live 호출 성공·최신성 확인 시각이 아니다. timezone이 포함된 시각만 허용한다.
- `promulgation_date`: 원자료의 공포일이다. 유효한 날짜만 exporter `created_at`으로 매핑한다.
  UTC+09 자정 매핑은 교환용 표현이며 실제 공포 시각을 주장하지 않는다.
- `enforcement_date`: 원자료에 적힌 시행일이다. 미래 시행이면 별도 표기하지만 현재 적용성은 판단하지 않는다.
  기준 시각을 한국(UTC+09) 날짜로 변환해 비교하므로 UTC 자정 경계와 혼동하지 않는다.
- `source_modified_at`: 원본 frontmatter 주장이다. 관측 시각과 구분하고 최신성 검증 근거로 사용하지 않는다.
  null 또는 timezone이 포함된 유효한 시각만 받는다. snapshot의 `upstream_commit`은 null 또는
  40자리 hex만 허용한다. 형식 검사는 해당 커밋의 진위 검증을 대신하지 않는다.
- `revision`: 내용 hash 변경이다. Git 커밋·내용 변경만으로 법률상 개정 또는 대체를 단정하지 않는다.
- `amendment_status`, `supersession_status`, `legal_effect_status`: 현재 모두 `not_determined`다.
  새 버전 발견, 폐지 표기, 파일 부재로 이전 근거를 자동 삭제·대체하지 않는다.
  `lifecycle=active`는 저장 레코드 상태이며 법률 시행 여부가 아니다.

## 최신성·충돌

어댑터의 상태는 `unknown / stale / conflicting`이다. 관측 기준일 `as_of`를 호출자가 명시한다.
`stale_after_days=N`은 **관측 시각의 나이**가 N일을 초과할 때만 stale로 정하는 선택 정책이다.
N은 0부터 999,999,999까지의 정수 또는 null이며 범위를 벗어나면 `ValueError`로 거절한다.
N일과 같으면 stale이 아니지만 여전히 unknown이다. 기간이 짧아도 최신 법령이라는 상태는 만들지 않는다.
정책 없음·관측 없음·미래 관측은 unknown이며 사유 코드를 반환한다. 잘못된 날짜·시간대·정책은 거절한다.

같은 공식 법령 ID·법령구분·section·조문인데 내용 hash 또는 공포/시행일이 다르면
`conflicting`을 우선하고 모든 근거를 보존한다. 날짜 순으로 승자를 고르지 않는다.
공식 ID가 없으면 같은 종류의 같은 문서 ID 안에서만 비교한다. 제목만 같은 자료의 동일성은 미확정이다.
개정 이력의 서로 다른 판본도 이 계약에서는 사람의 적용 시점 검토가 필요한 충돌 후보다.
라벨 없는 부칙의 `identity_strength=section_content_weak`는 section 본문 hash에 의존한다.
내용이 바뀌면 section 키도 달라져 충돌을 놓치고 unknown이 될 수 있다. `path_fallback_weak`도
공식 ID가 없는 약한 식별자다. unknown을 출처 일치나 충돌 없음으로 해석하지 않고 사람이 원문을 비교한다.

기존 exporter의 `observed_unverified / stale_by_explicit_policy / conflicting_source`는 과거 메타데이터
어휘로 보존한다. 새 어댑터는 원래 상태를 최신성 증거로 신뢰하지 않고 위 정책으로 다시 분류한다.
기존 `classify_freshness()`의 원본변경일 기반 선택 정책은 새 관측 나이 정책과 다르다.

## 중앙 Knowledge 대조

읽기 전용 비교 대상은 중앙 HEAD `96d02636a6132c4be05e7b49d43a9c78af210ad7`이다.
`tests/fixtures/central-knowledge-v2-contract.json`과 v2 스키마에 출처·SHA-256을 고정했다.
중앙 파일·서비스·DB는 바꾸거나 호출하지 않았다.

| 대상 | 확인 및 차이 |
| --- | --- |
| 과거 기본 v1 | source enum에 법령이 없어 거절한다. 과거 fixture·기본 선택을 유지한다. |
| 현재 명시적 v2 | 법령 source enum이 있다. 나머지 필드·제약은 v1과 같다. 새 합성 JSONL을 경로+SHA 명시로 대조한다. |
| 기존 동결 JSONL | 필드 스키마 대조와 법률 메타데이터 안전성은 별개다. 과거 산출물을 현행 검증 자료로 재발행하지 않는다. |
| 새 SQLite | 누락됐던 `deleted_at` nullable 열을 추가했다. `metadata_json`을 object, 0/1을 boolean으로 복원해 같은 v2 문서 검증과 JSONL 전체 필드 parity를 검사한다. |
| 중앙 SQLite | 중앙 테이블은 `knowledge_documents`이며 `imported_at_ms`, 별도 chunks/import jobs가 있다(`src/knowledge.rs`). 로컬 `documents`·FTS는 export 형식이다. 중앙 DB 교체·직접 SQLite importer 호환을 주장하지 않는다. 중앙의 적용 경로는 JSONL import 소유권 아래 있다. |

`reconcile_knowledge_contract.py --sqlite`는 닫힌 로컬 export DB만 `mode=ro&immutable=1`로 읽는다.
live WAL DB에는 사용하지 않는다. 누락 열·잘못된 boolean·전체 필드 불일치를 거절한다.
CLI는 보고서를 출력하고 적합이면 종료 0, 부적합이면 종료 1을 반환한다(JSONL 단독도 동일).
여기서 전체 필드 parity는 JSONL과 `documents` 표의 문서 필드 비교다.
`documents_fts` 검색 색인의 내용·정합성 검사는 포함하지 않는다.
기존 동결 SQLite의 `deleted_at` 누락은 보고하며 자동 ALTER/마이그레이션하지 않는다.
새 결과의 스키마 적합성은 중앙 import 성공·실행 guard 완성·법적 정확성을 뜻하지 않는다.

실제 읽기 전용 대조 결과: 기존 JSONL **1,695건은 v2 필드 검증 통과**, 기존 SQLite는
`no such column: deleted_at`으로 실패했다. 새 합성 출력 **1건은 JSONL/SQLite 모두 v2 검증과
전체 필드 parity 통과**다. 기존 출력 3종은 수정하지 않았다. 중앙 런타임 source allowlist에도
법령 키가 이미 있으므로 과거 D3의 enum/등록 불가 기록을 현재의 전체 상태로 일반화하지 않는다.
중앙 실행 guard·운영 import·지원 어댑터 채택 검증은 별도로 남는다.

```bash
python3 scripts/reconcile_knowledge_contract.py <synthetic.jsonl> \
  --sqlite <synthetic.db> \
  --schema <절대경로/knowledge-document.v2.schema.json> \
  --expected-schema-sha256 71f422c97491c6dc9ab99fa643d89ff1f83dbd36d96ab02f32a669310624731e
```

## 안전·재현 시험과 분리

새 exporter 문서와 manifest, 어댑터 응답에 `legal_advice=false`, `human_review_required=true`를 기록한다.
기존 동결 `exports/integration/korean-law-backend.manifest.json`에는 과거 8765 포트가 남아 있다.
이 장비에서는 해당 주소를 호출하지 않는다(`AGENTS.md`). 새 합성 manifest만 18765를 사용하며
동결 manifest를 실행 설정으로 사용하지 않는다.
어댑터의 network/file/central write, filing/submission/account action capability는 모두 false다.
어댑터는 메모리 자료만 받고 stdout·파일·네트워크 출력이나 subprocess 실행도 하지 않는다.
exporter 자체는 별도의 명시적 로컬 파일 쓰기 명령이다. dry-run 어댑터와 혼동하지 않는다.

```python
from law_adapter.dry_run import preview

result = preview(requested_kind="all_offline", as_of="2026-11-01T00:00:00Z",
                 snapshot_documents=snapshot_documents, user_documents=user_documents,
                 stale_after_days=30)
```

`tests/fixtures/legal-evidence-cases.json`은 실제 법령이 아닌 합성 인용, 미래 시행일,
정책 경계, 오래된/미래/누락 관측, 상충하는 근거를 고정한다.
`test_dry_run_adapter.py`는 live 무대체, 사용자 신뢰 표지 격리, hash 변조, 날짜 오류,
충돌 보존 및 I/O 금지를 검증한다. `test_sqlite_knowledge_contract.py`는 실제 중앙 v2의
고정 사본으로 전체 필드 parity, tombstone 날짜, 기존 열 누락·DB 변조를 검증한다.

upstream clone은 `upstreams/`, 패치된 실험 runtime은 `.runtime/`, 준비·export·가짜 API 실험은
`scripts/`에 남긴다. 지원 후보 계약 코드는 `law_adapter/`로 분리했으며 upstream을 import하지 않는다.
이 분리는 지원 승격을 의미하지 않는다. 라이선스 범위·공식 최신성·실제 API·중앙 guard·owner 승인이 남아 있다.
