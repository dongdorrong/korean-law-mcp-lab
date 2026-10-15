# Integrated Practice

이 문서는 `legalize-kr`와 `korean-law-mcp`를 함께 쓰는 실습 흐름입니다. `legalize-kr`는 로컬 Git 데이터로 재현 가능한 원문/이력을 확인하고, `korean-law-mcp`는 법제처 API와 판례/해석례/자치법규 등 외부 검색을 연결하는 역할로 봅니다.

## 실습 전제

```bash
cd <repo>
```

실제 MCP/CLI API 호출에는 `LAW_OC`가 필요합니다.

```bash
export LAW_OC='발급받은-법제처-OC-키'
```

## 시나리오 1: 민법 제103조 영향 분석

목표: 로컬 법령 원문에서 조문을 확인하고, MCP로 판례/해석례/영향 그래프를 확장합니다.

### 1. 로컬 원문 확인

```bash
rg -n '제103조' upstreams/legalize-kr/kr/민법/법률.md
sed -n '636,648p' upstreams/legalize-kr/kr/민법/법률.md
```

### 2. MCP 영향 그래프 실행

```bash
cd upstreams/korean-law-mcp
node build/cli.js impact_map --lawName 민법 --jo 제103조
```

확인 포인트:

- 역방향: 해당 조문을 인용한 판례, 헌재 결정, 해석례, 행정심판, 자치법규
- 정방향: 제103조 본문 안에서 다른 법령을 인용하는지
- Mermaid 그래프가 생성되는지

## 시나리오 2: 민법 제750조 인용 검증

목표: LLM이나 사람이 쓴 법률 문서의 조문 인용을 검증합니다.

### 1. 로컬 원문 확인

```bash
rg -n '제750조' upstreams/legalize-kr/kr/민법/법률.md
```

### 2. MCP 인용 검증

```bash
cd upstreams/korean-law-mcp
node build/cli.js verify_citations --text '민법 제750조는 불법행위 손해배상을 규정하고, 형법 제9999조는 가중처벌을 규정한다.'
```

확인 포인트:

- 실제 조문과 가짜 조문을 구분하는지
- 실패 결과가 LLM이 추측하지 않도록 명확한 마커를 포함하는지

## 시나리오 3: 개인정보 보호법 시점 비교

목표: `legalize-kr`의 Git 이력과 `korean-law-mcp`의 time travel 계열 기능을 비교합니다.

### 1. 로컬 최신 원문 메타데이터

```bash
sed -n '1,24p' upstreams/legalize-kr/kr/개인정보보호법/법률.md
```

### 2. 과거 이력 찾기

```bash
git -C upstreams/legalize-kr log --oneline --max-count=10 -- kr/개인정보보호법/법률.md
git -C upstreams/legalize-kr log --before='2021-01-01' -1 --oneline -- kr/개인정보보호법/법률.md
```

### 3. MCP 자연어 시점 비교

```bash
cd upstreams/korean-law-mcp
node build/cli.js 개인정보보호법 2020-01-01 vs 2025-11-01
```

확인 포인트:

- `legalize-kr`는 Git commit 기준으로 재현성이 좋습니다.
- `korean-law-mcp`는 자연어 질의와 법제처 API 기반 상세 비교가 강점입니다.
- 두 결과의 기준일, 시행일, 공포일을 혼동하지 않도록 기록합니다.

## 시나리오 4: 법률과 시행령 연결

목표: 로컬 데이터에서 법률/시행령 구조 차이를 보고, MCP의 3단 비교 도구로 확장합니다.

### 1. 로컬 diff

```bash
diff -u upstreams/legalize-kr/kr/개인정보보호법/법률.md upstreams/legalize-kr/kr/개인정보보호법/시행령.md | sed -n '1,120p'
```

### 2. MCP 체계 분석

```bash
cd upstreams/korean-law-mcp
node build/cli.js chain_law_system --query 개인정보보호법
```

확인 포인트:

- 법률, 시행령, 시행규칙의 위임 관계
- 별표/서식이 시행령에 붙는지
- 로컬 diff로는 보기 어려운 관련 법령 연결을 MCP가 보강하는지

## 시나리오 5: 근로기준법 조문 리서치

목표: 특정 조문을 원문, 판례, 해석례 흐름으로 확인합니다.

### 1. 로컬 조문 검색

```bash
rg -n '제74조|임산부|출산' upstreams/legalize-kr/kr/근로기준법/법률.md
```

### 2. MCP 질의

```bash
cd upstreams/korean-law-mcp
node build/cli.js 근로기준법 제74조 해석례
node build/cli.js search_decisions --domain interpretation --query '근로기준법 제74조'
```

확인 포인트:

- 법령 본문과 해석례의 차이
- 최신 시행일과 질의 회신일의 차이
- 관련 판례가 필요한지

## 결과 기록 템플릿

실습 결과를 남길 때는 아래 형식을 권장합니다.

```markdown
## 실습명

- 날짜:
- 질문:
- 사용한 소스:
  - legalize-kr commit:
  - korean-law-mcp commit:
  - LAW_OC 사용 여부:
- 실행 명령:
- 핵심 결과:
- 원문/출처:
- 불확실성:
- 다음 확인:
```

## 두 프로젝트의 역할 분담

| 질문 | 우선 도구 |
| --- | --- |
| 현재 법령 원문을 로컬에서 빠르게 보고 싶다 | `legalize-kr` |
| 특정 날짜 전후의 Git 이력을 보고 싶다 | `legalize-kr` |
| 법제처 API 최신 검색 결과가 필요하다 | `korean-law-mcp` |
| 판례, 해석례, 행정심판까지 확장하고 싶다 | `korean-law-mcp` |
| LLM 답변의 조문 인용을 검증하고 싶다 | `korean-law-mcp verify_citations` |
| 법률/시행령/시행규칙 위임 구조를 보고 싶다 | 둘 다 사용 |

## 품질 체크리스트

- 법령명, 조문번호, 시행일자를 함께 기록했는가?
- Git commit 기준과 법제처 API 기준을 구분했는가?
- MCP 결과가 없을 때 LLM이 추측하지 않도록 원문 확인을 했는가?
- 법률, 시행령, 시행규칙을 혼동하지 않았는가?
- 실습 결과를 법률 자문처럼 단정하지 않았는가?
