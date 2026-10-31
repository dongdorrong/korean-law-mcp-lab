# korean-law-mcp Guide

## 무엇을 실습할 수 있나

`korean-law-mcp`는 법제처 OpenAPI를 MCP 서버와 CLI로 호출하는 TypeScript 프로젝트입니다. AI 클라이언트에서는 MCP 도구로, 터미널에서는 `korean-law` CLI로 사용할 수 있습니다.

## 로컬 위치

```bash
cd <repo>/upstreams/korean-law-mcp
```

## 요구사항

`package.json` 기준 요구사항은 Node.js `>=20.19.0`입니다.

현재 이 환경에서는 Node.js `v18.20.8`로 다음까지는 검증했습니다.

- `npm ci`: 성공, engine warning 발생
- `npm run build`: 성공
- `node build/cli.js list --json`: 성공
- `node build/cli.js explain 민법 제1조`: 성공
- HTTP 서버 `/health`: 성공

장기 실습과 실제 API 호출은 Node.js 20.19 이상에서 진행하는 것을 권장합니다.

## 설치 및 빌드

```bash
npm ci
npm run build
```

검증 결과:

```text
added 129 packages
found 0 vulnerabilities
```

## API 키 설정

실제 법제처 API 호출에는 `LAW_OC`가 필요합니다.

```bash
export LAW_OC='발급받은-법제처-OC-키'
```

`.env`로 관리하려면 예시 파일을 복사합니다.

```bash
cp ../../examples/korean-law-mcp.env.example .env
```

`.env`에는 실제 키를 넣되, Git에 커밋하지 마세요.

## API 키 없이 가능한 검증

```bash
node build/cli.js list --json
node build/cli.js help search_law
node build/cli.js explain 민법 제1조
```

검증된 `explain` 결과:

```text
질의: "민법 제1조"
도구: search_law
근거: 법령명 + 조문번호 → 해당 조문 직접 조회 (법령 검색 → 조문 조회 자동 연결)
파라미터: {
  "query": "민법"
}
파이프라인:
  → get_law_text({"jo":"제1조"})
```

## CLI 실습

```bash
node build/cli.js search_law --query 민법
node build/cli.js get_law_text --lawId 001706 --jo 제1조
node build/cli.js verify_citations --text '민법 제750조는 불법행위 손해배상을 규정한다. 형법 제9999조도 존재한다.'
node build/cli.js impact_map --lawName 민법 --jo 제103조
```

자연어 라우팅도 사용할 수 있습니다.

```bash
node build/cli.js 민법 제1조
node build/cli.js 개인정보보호법 2020-01-01 vs 2025-11-01
node build/cli.js 전세금 못 받았어
```

## HTTP MCP 서버 실습

```bash
LAW_OC='발급받은-법제처-OC-키' node build/index.js --mode http --port 18765
```

다른 터미널에서 확인합니다.

```bash
curl -s http://127.0.0.1:18765/health
```

검증된 응답:

```json
{"status":"ok","timestamp":"2026-06-07T08:05:19.803Z"}
```

개발용으로 CORS 경고가 뜰 수 있습니다.

```text
CORS_ORIGIN 미설정 — 모든 도메인 허용 중. 프로덕션에서는 CORS_ORIGIN 환경변수를 설정하세요.
```

운영 또는 공유 환경에서는 `CORS_ORIGIN`을 제한하세요.

## MCP 클라이언트 설정 예시

### 로컬 STDIO

```json
{
  "mcpServers": {
    "korean-law": {
      "command": "korean-law-mcp",
      "env": {
        "LAW_OC": "발급받은-법제처-OC-키"
      }
    }
  }
}
```

### 로컬 개발 빌드 직접 실행

```json
{
  "mcpServers": {
    "korean-law-local": {
      "command": "node",
      "args": [
        "<repo>/upstreams/korean-law-mcp/build/index.js"
      ],
      "env": {
        "LAW_OC": "발급받은-법제처-OC-키"
      }
    }
  }
}
```

### HTTP MCP

```json
{
  "mcpServers": {
    "korean-law-http": {
      "url": "http://127.0.0.1:18765/mcp"
    }
  }
}
```

## 직접 노출되는 핵심 도구

`src/tool-registry.ts` 기준 MCP 클라이언트에 직접 노출되는 도구는 다음 그룹입니다.

| 그룹 | 도구 |
| --- | --- |
| 체인 | `chain_full_research`, `chain_law_system`, `chain_action_basis`, `chain_dispute_prep`, `chain_amendment_track`, `chain_ordinance_compare`, `chain_procedure_detail`, `chain_document_review` |
| 법령 | `search_law`, `get_law_text`, `get_annexes` |
| 통합 결정례 | `search_decisions`, `get_decision_text` |
| 메타 | `discover_tools`, `execute_tool` |
| 검증/분석 | `verify_citations`, `impact_map` |

내부 도구는 더 많이 등록되어 있고, 필요할 때 `discover_tools`와 `execute_tool`로 접근합니다.

## 자주 쓰는 워크플로우

### 법령명 확인 후 조문 조회

```bash
node build/cli.js search_law --query 근로기준법
node build/cli.js get_law_text --mst '검색결과-MST' --jo 제74조
```

### 법률 문서 인용 검증

```bash
node build/cli.js verify_citations --text '민법 제750조, 근로기준법 제60조 제1항, 형법 제9999조'
```

### 판례/해석례 통합 검색

```bash
node build/cli.js search_decisions --domain precedent --query '민법 제103조'
node build/cli.js search_decisions --domain interpretation --query '개인정보보호법 국외 이전'
```

### 전문 도구 탐색

```bash
node build/cli.js discover_tools --query '법령 용어'
node build/cli.js execute_tool --json-input '{"tool_name":"parse_jo_code","params":{"jo":"제10조의2"}}'
```

## 문제 해결

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `LAW_OC 환경변수 또는 --apiKey 옵션이 필요합니다.` | API 키 미설정 | `export LAW_OC='키'` 설정 |
| engine warning | Node 버전 낮음 | Node.js 20.19 이상 사용 |
| 법제처 응답 실패 | OC 키, Referer, 사내망, 인증서 문제 | `LAW_API_PROTOCOL`, `LAW_REFERER`, 프록시 설정 검토 |
| HTTP 서버 CORS 경고 | `CORS_ORIGIN` 미설정 | 운영 환경에서는 허용 origin 지정 |
| 국세청 판례 fallback 실패 | 사내 HTTPS 프록시/인증서 문제 | `LAW_EXTERNAL_HTTPS_PROXY` 설정, TLS 우회는 진단용으로만 사용 |
