# TODO — fordongdorrong 연동 후속 작업

작성일: 2026-06-27

## 현재 완료

- `quant`는 이번 범위에서 제외.
- `korean-law-mcp-lab`에 `fordongdorrong` 사전 연동용 export 스크립트 추가.
- API 키가 없어도 `legalize-kr` 로컬 Markdown snapshot을 조문 단위 Knowledge JSONL/SQLite로 export.
- API 키가 있으면 `LAW_OC` 값을 저장하지 않고 manifest에 live MCP 사용 가능 상태만 표시.
- SQLite `documents` 테이블과 가능한 경우 FTS5 `documents_fts` 생성.
- 안전 경계: 법률 자문 아님, 최신성/사건 판단은 법제처 원문·MCP·전문가 검토 필요.

## 다음 작업

1. `fordongdorrong` 쪽 importer 계약 확인
   - JSONL ingest가 있는지
   - SQLite `documents` 테이블을 읽는지
   - RAG metadata filter 이름이 맞는지
2. `fordongdorrong` 답변 guard 설계
   - `law_title`, `law_type`, `article_no`, `enforcement_date`, `source_path` citation 강제
   - `legal_advice=false`를 system/policy guard에 반영
3. `LAW_OC` 발급 후 live MCP smoke
   - `node build/index.js --mode http --port 8765`
   - `/health` 확인
   - 대표 질의 `search_law`, `verify_citations`, `impact_map` 확인
4. 로컬 export와 live MCP 병합 전략
   - 기본 검색: SQLite/JSONL
   - 최신성/판례/해석례 확장: live MCP
   - live 실패 시 local-only fallback
5. sparse checkout 확장 후보
   - 상법
   - 형법
   - 민사소송법
   - 전자상거래법/개인정보보호 관련 하위 법령
6. export 품질 개선 후보
   - 조문 제목 정규화
   - 부칙 별도 chunking
   - 별표/서식 metadata 처리
   - 개정 이력 document 추가

## 검증 명령

```bash
python3 -m compileall -q scripts
python3 -m unittest discover -s tests
python3 scripts/export_fordongdorrong_backend.py --print-summary
python3 - <<'PY'
import json, sqlite3
print(json.loads(open('exports/integration/korean-law-backend.manifest.json', encoding='utf-8').read())['backend_id'])
with sqlite3.connect('exports/sqlite/korean-law.db') as conn:
    print(conn.execute('select count(*) from documents').fetchone()[0])
PY
```
