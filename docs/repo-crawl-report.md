# Repo Crawl Report

검토일: 2026-06-07

## 크롤링 범위

| 저장소 | 원격 | 로컬 경로 | 기준 커밋 |
| --- | --- | --- | --- |
| legalize-kr | https://github.com/legalize-kr/legalize-kr | `upstreams/legalize-kr` | `874b585` |
| korean-law-mcp | https://github.com/chrisryugj/korean-law-mcp | `upstreams/korean-law-mcp` | `f71b28c` |

## 원본 요약

`legalize-kr/legalize-kr`는 대한민국 법령을 Markdown 파일로 저장하고, 각 개정을 Git commit으로 관리하는 데이터 저장소입니다. README 기준 구조는 `kr/{법령명}/{법령구분}.md`이며, 법률/시행령/시행규칙이 같은 법령 디렉토리 아래에 모입니다.

`chrisryugj/korean-law-mcp`는 법제처 OpenAPI를 MCP 서버와 CLI로 사용할 수 있게 만든 TypeScript 프로젝트입니다. README와 `package.json` 기준 현재 버전은 `4.1.1`이고, 법령/판례/행정규칙/자치법규/조약/해석례 검색, 인용 검증, 영향 그래프, 시점 비교, 상황별 안내를 핵심 기능으로 둡니다.

## 로컬 수집 방식

`legalize-kr`는 데이터 규모가 크므로 파일 checkout은 sparse로 제한했습니다. 다만 이 프로젝트의 핵심인 법령 이력 실습을 위해 전체 commit history는 가져왔습니다.

체크아웃한 대표 법령:

| 법령 | 파일 |
| --- | --- |
| 민법 | `kr/민법/법률.md` |
| 개인정보 보호법 | `kr/개인정보보호법/법률.md`, `시행령.md` |
| 근로기준법 | `kr/근로기준법/법률.md`, `시행령.md`, `시행규칙.md` |

`korean-law-mcp`는 전체 저장소를 얕은 클론으로 가져왔고, 의존성 설치와 빌드를 검증했습니다.

## 주요 발견

### legalize-kr

- 현재 전체 이력 수: `83,881` commits
- 대표 법령 Markdown은 YAML frontmatter와 본문으로 구성됩니다.
- 예: `upstreams/legalize-kr/kr/민법/법률.md`는 `제목`, `법령MST`, `법령ID`, `소관부처`, `공포일자`, `시행일자`, `출처`를 포함합니다.
- 민법 최신 메타데이터 예시:
  - `법령MST: 284415`
  - `법령ID: '001706'`
  - `공포일자: 2026-03-17`
  - `시행일자: 2026-03-17`
- README는 force-push 가능성을 명시합니다. 이 저장소를 장기 참조할 때 commit hash를 영구 식별자로 고정하면 위험합니다.

검증한 명령:

```bash
git -C upstreams/legalize-kr rev-list --count HEAD
git -C upstreams/legalize-kr log --oneline --max-count=5 -- kr/민법/법률.md
git -C upstreams/legalize-kr log --before='2025-01-01' -1 --oneline -- kr/민법/법률.md
git -C upstreams/legalize-kr show '89208f80b7:kr/민법/법률.md' | sed -n '1,30p'
```

### korean-law-mcp

- `package.json` 기준 버전: `4.1.1`
- `package.json`의 Node 요구사항: `>=20.19.0`
- 현재 로컬 Node: `v18.20.8`
- `npm ci`는 engine warning과 함께 성공했습니다.
- `npm audit` 결과: `0 vulnerabilities`
- `npm run build` 성공
- API 키 없이 가능한 CLI 명령 검증:
  - `node build/cli.js list --json`
  - `node build/cli.js help search_law`
  - `node build/cli.js explain 민법 제1조`
- API 키 없이 실제 API 호출 시 명확한 오류 확인:

```text
LAW_OC 환경변수 또는 --apiKey 옵션이 필요합니다.
API 키 발급: https://open.law.go.kr/LSO/openApi/guideResult.do
```

- HTTP 서버 기동 및 health 확인:

```bash
node build/index.js --mode http --port 8765
curl -s http://127.0.0.1:8765/health
```

결과:

```json
{"status":"ok","timestamp":"2026-06-07T08:05:19.803Z"}
```

## 문서 최신성 주의

`korean-law-mcp`의 README와 `package.json`은 v4.1.1 기준으로 보입니다. 반면 `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`에는 v2/v3 문구와 오래된 도구 수 표현이 일부 남아 있습니다.

실습에서는 다음 순서로 신뢰도를 두는 것이 안전합니다.

1. `package.json`
2. `README.md`
3. `src/tool-registry.ts`
4. `docs/*.md`

## 참고 링크

- legalize-kr: https://github.com/legalize-kr/legalize-kr
- korean-law-mcp: https://github.com/chrisryugj/korean-law-mcp
- 법제처 OpenAPI: https://open.law.go.kr
