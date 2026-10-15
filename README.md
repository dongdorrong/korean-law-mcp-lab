# Korean Law MCP Lab

검토일: 2026-06-07

이 랩은 `legalize-kr/legalize-kr`와 `chrisryugj/korean-law-mcp`를 함께 실습하기 위한 작업 공간입니다. 목표는 한국 법령 데이터를 Git으로 탐색하는 방법과, 법제처 OpenAPI 기반 MCP/CLI 도구를 AI 클라이언트에서 활용하는 방법을 한 곳에서 비교해 보는 것입니다.

> 주의: 이 저장소의 결과물은 개발/리서치 실습용입니다. 실제 법률 판단이나 사건 대응에는 최신 원문 확인과 전문가 검토가 필요합니다.

## fordongdorrong 사전 연동

`fordongdorrong` repository를 건드리지 않고, 이 랩 안에서 RAG/SQLite importer가 읽을 수 있는 산출물을 만듭니다. API 키 유무와 관계없이 동작합니다.

```bash
cd <repo>
python3 scripts/export_fordongdorrong_backend.py --print-summary
```

생성 산출물:

| Path | 용도 |
| --- | --- |
| `exports/knowledge/korean-law.jsonl` | RAG/Knowledge Store import용 조문 단위 JSONL |
| `exports/sqlite/korean-law.db` | SQLite importer/FTS 검색용 DB |
| `exports/integration/korean-law-backend.manifest.json` | local export와 optional live MCP 연결 manifest |

동작 모드:

- `LAW_OC` 없음: 로컬 `legalize-kr` Markdown snapshot 기반 JSONL/SQLite만 사용.
- `LAW_OC` 있음: 같은 JSONL/SQLite를 만들고, manifest에 live `korean-law-mcp` 사용 가능 상태를 표시. 키 값은 저장하지 않음.

상세 계약은 [`docs/fordongdorrong-integration.md`](docs/fordongdorrong-integration.md)를 봅니다.

## 원본 저장소

| 저장소 | 로컬 경로 | 역할 |
| --- | --- | --- |
| https://github.com/legalize-kr/legalize-kr | `upstreams/legalize-kr` | 대한민국 법령 Markdown 데이터와 Git 개정 이력 |
| https://github.com/chrisryugj/korean-law-mcp | `upstreams/korean-law-mcp` | 법제처 OpenAPI 기반 MCP 서버 및 CLI |

## 로컬 구조

```text
korean-law-mcp-lab/
├── README.md
├── docs/
│   ├── repo-crawl-report.md
│   ├── legalize-kr-guide.md
│   ├── korean-law-mcp-guide.md
│   ├── integrated-practice.md
│   └── fordongdorrong-integration.md
├── exports/
│   ├── integration/
│   ├── knowledge/
│   └── sqlite/
├── examples/
│   └── korean-law-mcp.env.example
├── scripts/
└── upstreams/
    ├── legalize-kr/
    └── korean-law-mcp/
```

## 빠른 시작

원본 저장소 클론은 용량과 중첩 Git 이슈를 피하기 위해 이 랩 저장소에 커밋하지 않습니다. 새 환경에서 시작할 때는 먼저 bootstrap 스크립트를 실행하세요.

```bash
cd <repo>
chmod +x scripts/bootstrap-upstreams.sh
./scripts/bootstrap-upstreams.sh
```

### 1. legalize-kr 데이터 확인

```bash
cd <repo>

sed -n '1,40p' upstreams/legalize-kr/kr/민법/법률.md
rg -n '제750조|제103조' upstreams/legalize-kr/kr/민법/법률.md
git -C upstreams/legalize-kr log --oneline --max-count=5 -- kr/민법/법률.md
```

### 2. korean-law-mcp CLI 확인

```bash
cd <repo>/upstreams/korean-law-mcp

npm run build
node build/cli.js list --json
node build/cli.js explain 민법 제1조
```

실제 법제처 API 호출은 `LAW_OC`가 필요합니다.

```bash
export LAW_OC='발급받은-법제처-OC-키'
node build/cli.js search_law --query 민법
```

### 3. MCP HTTP 서버 확인

```bash
cd <repo>/upstreams/korean-law-mcp
LAW_OC='발급받은-법제처-OC-키' node build/index.js --mode http --port 8765
curl http://127.0.0.1:8765/health
```

## 문서

| 문서 | 용도 |
| --- | --- |
| `docs/repo-crawl-report.md` | 두 저장소 크롤링/검증 결과 요약 |
| `docs/legalize-kr-guide.md` | Git 기반 법령 데이터 실습 |
| `docs/korean-law-mcp-guide.md` | MCP/CLI 설치, 설정, 실행 가이드 |
| `docs/integrated-practice.md` | 두 프로젝트를 함께 쓰는 통합 실습 시나리오 |
| `docs/fordongdorrong-integration.md` | `fordongdorrong` RAG/SQLite 연동 계약 |

## 현재 검증 상태

| 항목 | 결과 |
| --- | --- |
| `legalize-kr` 커밋 이력 | 83,881개 확인 |
| `legalize-kr` 대표 sparse checkout | 민법, 개인정보보호법, 근로기준법 |
| `korean-law-mcp` 버전 | `4.1.1` |
| `npm ci` | 성공, 취약점 0건 |
| `npm run build` | 성공 |
| CLI `list`, `help`, `explain` | 성공 |
| CLI 실제 API 호출 | `LAW_OC` 미설정 시 명확한 오류 확인 |
| HTTP `/health` | `{"status":"ok"}` 확인 |
| fordongdorrong export | JSONL/SQLite/manifest 생성 확인 |

## 권장 다음 작업

1. `exports/integration/korean-law-backend.manifest.json`를 `fordongdorrong` importer 계약과 대조합니다.
2. 법제처 OpenAPI 인증키가 있으면 `LAW_OC`로 설정하고 live MCP smoke를 진행합니다.
3. `docs/korean-law-mcp-guide.md`의 CLI 실습을 실제 API 호출까지 진행합니다.
4. `docs/integrated-practice.md`의 시나리오를 따라 Git 데이터와 MCP 결과를 비교합니다.

## 2026-10-15 repo-local 안전성 업데이트

위의 2026-06 실습·검증 표는 **당시 이력**이며 현재 법령 최신성이나 live 인증 성공의 증거가 아닙니다. 이번 작업은 기존 tracked `exports/`와 기존 upstream checkout을 갱신하지 않았습니다. API 키가 있어도 exporter는 실제 LAW_OC 호출을 하지 않으며 `live_verified=false`입니다. 실제 호출 예시는 별도 승인 전 실행하지 않습니다.

- 재현 검증: `./scripts/verify.sh` (합성 자료·임시 출력만 사용).
- upstream 준비: `./scripts/bootstrap-upstreams.sh`는 `upstreams.lock.json`의 SHA만 준비하며, `--propose-update`는 후보만 출력합니다. `legalize-kr` 라이선스는 미확인입니다.
- 신규 export의 `created_at`은 유효한 공포일 또는 null, `updated_at`은 관측 시각입니다. 법적 시행일, 원본 변경일, live 검증 시각은 별도 metadata입니다. snapshot은 미검증입니다.
- 첫 생성 이후 **기존 고정 경로 3개는 그대로 유지**하고, 새 세대는 불변 `.law-generations/`에 기록한 뒤 `.current.json` 포인터 하나를 교체합니다. 새 소비자는 `read_current_generation()`으로 포인터를 고정·검증해 읽어야 합니다. 고정 경로만 읽는 기존 소비자는 이전 완전 세대를 계속 읽지만 최신 세대로 자동 이동하지 않습니다. 여러 파일을 하나의 원자적 교체라고 주장하지 않습니다.
- `--migration-report`는 `--previous-jsonl`을 반드시 요구하고, 기존 ID의 모호한 대응을 unresolved로 보고합니다. 실제 migration은 하지 않습니다.
- 중앙 Knowledge v1은 현재 법령 `source_id`를 허용하지 않습니다. `scripts/reconcile_knowledge_contract.py`는 pinned schema 전체에 대한 offline dry-run을 수행하며 중앙 쓰기를 하지 않습니다.

세부 검증·잔여 gate는 `docs/completion-ledger.md` 및 `docs/fordongdorrong-integration.md`의 최신 절을 참조하십시오.

첫 고정 경로 발행의 journal은 임시 파일에 완전히 기록·fsync한 뒤 같은 디렉터리의 하드링크로 최종 이름을 배타적으로 발행합니다. 다른 발행자가 먼저 journal을 만들었으면 덮어쓰지 않고 실패합니다. 출력 발행 도중 중단되면 `.law-first-publish.journal.json`을 남기고 재시도를 거절합니다. `recover_first_publish(root, source_dir, jsonl, sqlite, manifest)`의 기본값은 **읽기 전용 dry-run**입니다. `apply=True`는 기록된 SHA의 부분 출력을 삭제하지 않고 `.law-recovery-*` 감사용 파일로 옮겨 검증합니다. 파일이 도중 교체되면 새 내용을 덮거나 삭제하지 않고 가능한 경우 원래 경로에 비파괴적으로 복원하며 journal을 보존합니다. 이전 버전의 잘린 journal은 출력 3종이 모두 없을 때만 격리할 수 있습니다. 감사 파일은 자동 삭제하지 않습니다. 기존 자료의 자동 정리는 하지 않습니다. 기존 고정 3종 파일은 개수·JSONL/SQLite parity·manifest 상태 검증을 통과해야 동결됩니다. `--limit` 및 명시적 빈 결과는 처음부터 immutable smoke 세대로만 만들며 고정 경로의 완전 기준선이 되지 않습니다.

Offline LAW_OC 오류 분류는 `scripts/live_contract.py`에 있으며, 잠긴 `korean-law-mcp`의 `LawApiClient.searchLaw()` XML 반환 계약을 `tests/fixtures/pinned-mcp-search-contract.json`에 해시로 고정해 합성 XML과 fake transport로만 검사합니다. 이 랩은 upstream 검색 parser보다 엄격하게 `LawSearch` root, 결과 수, 필수 law 필드·공포일자의 실제 달력 날짜 및 XML 오류를 검사하며, HTML/오류/불명확한 응답을 0건 성공으로 해석하지 않습니다. 실제 API 호출, 인증 성공, 법적 최신성 검증은 아닙니다.
