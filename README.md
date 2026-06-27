# Korean Law MCP Lab

검토일: 2026-06-07

이 랩은 `legalize-kr/legalize-kr`와 `chrisryugj/korean-law-mcp`를 함께 실습하기 위한 작업 공간입니다. 목표는 한국 법령 데이터를 Git으로 탐색하는 방법과, 법제처 OpenAPI 기반 MCP/CLI 도구를 AI 클라이언트에서 활용하는 방법을 한 곳에서 비교해 보는 것입니다.

> 주의: 이 저장소의 결과물은 개발/리서치 실습용입니다. 실제 법률 판단이나 사건 대응에는 최신 원문 확인과 전문가 검토가 필요합니다.

## fordongdorrong 사전 연동

`fordongdorrong` repository를 건드리지 않고, 이 랩 안에서 RAG/SQLite importer가 읽을 수 있는 산출물을 만듭니다. API 키 유무와 관계없이 동작합니다.

```bash
cd /home/dongdorrong/github/private/korean-law-mcp-lab
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
cd /home/dongdorrong/github/private/korean-law-mcp-lab
chmod +x scripts/bootstrap-upstreams.sh
./scripts/bootstrap-upstreams.sh
```

### 1. legalize-kr 데이터 확인

```bash
cd /home/dongdorrong/github/private/korean-law-mcp-lab

sed -n '1,40p' upstreams/legalize-kr/kr/민법/법률.md
rg -n '제750조|제103조' upstreams/legalize-kr/kr/민법/법률.md
git -C upstreams/legalize-kr log --oneline --max-count=5 -- kr/민법/법률.md
```

### 2. korean-law-mcp CLI 확인

```bash
cd /home/dongdorrong/github/private/korean-law-mcp-lab/upstreams/korean-law-mcp

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
cd /home/dongdorrong/github/private/korean-law-mcp-lab/upstreams/korean-law-mcp
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
