# fordongdorrong Integration Contract

작성일: 2026-06-27

이 문서는 `korean-law-mcp-lab`을 나중에 `fordongdorrong`의 법령 근거 백엔드로 붙이기 위한 사전 계약입니다. `fordongdorrong` repository는 이 작업에서 수정하지 않습니다.

## 목표

`LAW_OC` 법제처 API 키 유무와 관계없이 동작하는 연결 표면을 둔다.

- **키 없음**: `legalize-kr` 로컬 Markdown snapshot을 Knowledge JSONL/SQLite로 export해 RAG/SQLite importer가 바로 읽는다.
- **키 있음**: 위 로컬 export를 안정적인 기본 근거로 유지하면서 `korean-law-mcp` live MCP/API를 최신 검색, 판례/해석례, 영향 그래프 확장에 사용한다.

## 산출물

```text
exports/
├── integration/
│   └── korean-law-backend.manifest.json
├── knowledge/
│   └── korean-law.jsonl
└── sqlite/
    └── korean-law.db
```

생성 명령:

```bash
cd /home/dongdorrong/github/private/korean-law-mcp-lab
python3 scripts/export_fordongdorrong_backend.py --print-summary
```

## API 키 없는 모드

이 모드는 기본값이며 외부 API 호출을 하지 않습니다.

```bash
unset LAW_OC
python3 scripts/export_fordongdorrong_backend.py --print-summary
```

기대 동작:

- `exports/knowledge/korean-law.jsonl` 생성
- `exports/sqlite/korean-law.db` 생성
- `exports/integration/korean-law-backend.manifest.json` 생성
- manifest의 `local_export.requires_api_key=false`
- manifest의 `live_mcp.api_key_configured=false`

## API 키 있는 모드

법제처 OpenAPI 키가 있으면 같은 export를 생성하면서 manifest에 live MCP 사용 가능 상태를 표시합니다. 키 값은 저장하지 않습니다.

```bash
export LAW_OC='발급받은-법제처-OC-키'
python3 scripts/export_fordongdorrong_backend.py --print-summary
```

기대 동작:

- 로컬 JSONL/SQLite는 동일하게 생성
- manifest의 `live_mcp.api_key_configured=true`
- `LAW_OC` 실제 값은 JSONL/SQLite/manifest에 저장되지 않음

live MCP 실행 예:

```bash
cd /home/dongdorrong/github/private/korean-law-mcp-lab/upstreams/korean-law-mcp
LAW_OC='발급받은-법제처-OC-키' node build/index.js --mode http --port 8765
curl -s http://127.0.0.1:8765/health
```

## Knowledge JSONL 계약

각 줄은 하나의 조문 단위 문서입니다.

```json
{
  "source_id": "korean-law-mcp-lab",
  "document_id": "legalize-kr/kr/민법/법률.md#제1조-0001",
  "title": "민법 법률 제1조 법원",
  "body": "법령명/법령구분/조문/시행일자/원문...",
  "uri": "https://www.law.go.kr/법령/민법",
  "content_hash": "sha256:...",
  "created_at": "2026-03-17T00:00:00+09:00",
  "updated_at": "2026-03-17T00:00:00+09:00",
  "visibility": "private",
  "indexable": true,
  "metadata": {
    "kind": "law_article",
    "category": "korean_law",
    "law_title": "민법",
    "law_type": "법률",
    "article_no": "제1조",
    "enforcement_date": "2026-03-17",
    "verification_status": "local_official_text_snapshot",
    "metadata_source": "legalize-kr.git.markdown",
    "legal_advice": false
  }
}
```

## SQLite 계약

`exports/sqlite/korean-law.db`의 기본 테이블:

```sql
documents(
  source_id,
  document_id,
  title,
  body,
  uri,
  content_hash,
  created_at,
  updated_at,
  visibility,
  lifecycle,
  indexable,
  metadata_json
)
```

런타임 SQLite가 FTS5를 지원하면 `documents_fts(title, body, document_id)`도 생성합니다.

## fordongdorrong 권장 사용 방식

1. `manifest.local_export`를 읽어 JSONL/SQLite 경로와 문서 수를 확인한다.
2. RAG import는 `korean-law.jsonl` 또는 `korean-law.db.documents`를 사용한다.
3. 검색/답변 시 최소 citation으로 아래 metadata를 포함한다.
   - `law_title`
   - `law_type`
   - `article_no`
   - `enforcement_date`
   - `source_path`
4. `LAW_OC`가 설정되어 있고 live MCP가 떠 있으면 최신 검색·판례·해석례 확장에 사용한다.
5. `LAW_OC`가 없거나 live MCP가 실패하면 로컬 export만 사용하고, 최신성 한계를 사용자에게 표시한다.

## 안전 경계

- 이 백엔드는 법령 근거 검색/요약 보조용입니다.
- 실제 법률 판단, 사건 대응, 법률 자문처럼 단정하지 않습니다.
- 최신성·시행일·개정 여부가 중요한 질문은 법제처 원문/live MCP/전문가 검토로 재확인해야 합니다.
- API 키, 토큰, 쿠키, 비밀번호는 export 산출물에 저장하지 않습니다.
