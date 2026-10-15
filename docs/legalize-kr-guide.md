# legalize-kr Guide

## 무엇을 실습할 수 있나

`legalize-kr`는 법령 원문을 Markdown 파일로 다루면서 Git의 이력, diff, 특정 시점 조회 기능을 그대로 활용하게 해 줍니다. API 서버를 띄우지 않아도 법령 데이터 탐색, 개정 이력 확인, 문서 검색 실습이 가능합니다.

## 로컬 위치

```bash
cd <repo>
cd upstreams/legalize-kr
```

이 랩에서는 전체 파일 checkout 대신 대표 법령만 sparse checkout했습니다.

```text
kr/민법/법률.md
kr/개인정보보호법/법률.md
kr/개인정보보호법/시행령.md
kr/근로기준법/법률.md
kr/근로기준법/시행령.md
kr/근로기준법/시행규칙.md
```

## 데이터 구조

법령 파일은 YAML frontmatter와 Markdown 본문으로 구성됩니다.

```bash
sed -n '1,40p' kr/민법/법률.md
```

확인할 핵심 필드:

| 필드 | 의미 |
| --- | --- |
| `제목` | 정규화된 법령명 |
| `법령MST` | 법령 고유 관리번호 |
| `법령ID` | 법령 ID |
| `법령구분` | 법률, 대통령령, 부령 등 |
| `소관부처` | 담당 부처 |
| `공포일자` | 해당 버전의 공포일 |
| `시행일자` | 해당 버전의 시행일 |
| `출처` | law.go.kr 원문 링크 |

## 실습 1: 조문 찾기

```bash
rg -n '제103조|제750조' kr/민법/법률.md
```

검증된 예:

```text
kr/민법/법률.md:641:##### 제103조 (반사회질서의 법률행위)
kr/민법/법률.md:4096:##### 제750조 (불법행위의 내용)
```

## 실습 2: 키워드 검색

```bash
rg -n '개인정보 보호 원칙|정보주체|가명처리' kr/개인정보보호법/법률.md
```

넓은 범위를 검색하려면 checkout된 법령 전체를 대상으로 실행합니다.

```bash
rg -n '개인정보' kr/
```

## 실습 3: 법률과 시행령 비교

법률과 시행령은 같은 주제라도 구조가 다릅니다. `diff`로 보면 메타데이터, 위임 구조, 별표 차이를 빠르게 파악할 수 있습니다.

```bash
diff -u kr/개인정보보호법/법률.md kr/개인정보보호법/시행령.md | sed -n '1,120p'
```

`diff`는 차이가 있으면 exit code `1`을 반환합니다. 오류가 아니라 정상적인 비교 결과입니다.

## 실습 4: 개정 이력 보기

```bash
git log --oneline --max-count=5 -- kr/민법/법률.md
```

검증된 예:

```text
d611508170 법률: 민법 (일부개정)
89208f80b7 법률: 민법 (일부개정)
2a0cf37827 법률: 민법 (타법개정)
f52ba93d82 법률: 민법 (일부개정)
5604174b27 법률: 민법 (일부개정)
```

## 실습 5: 특정 날짜 이전 버전 찾기

```bash
git log --before='2025-01-01' -1 --oneline -- kr/민법/법률.md
```

검증된 예:

```text
89208f80b7 법률: 민법 (일부개정)
```

해당 시점의 파일 앞부분을 확인합니다.

```bash
git show '89208f80b7:kr/민법/법률.md' | sed -n '1,30p'
```

검증된 메타데이터:

```yaml
제목: 민법
법령MST: 265307
법령ID: '001706'
공포일자: 2024-09-20
시행일자: 2025-01-31
```

## 실습 6: 개정 커밋의 변경량 보기

```bash
git show --stat --oneline --no-renames d611508170 -- kr/민법/법률.md
```

검증된 예:

```text
d611508170 법률: 민법 (일부개정)
1 file changed, 31 insertions(+), 17 deletions(-)
```

실제 변경 본문은 다음처럼 봅니다.

```bash
git show --no-renames d611508170 -- kr/민법/법률.md | sed -n '1,180p'
```

## sparse checkout 범위 늘리기

다른 법령을 추가로 실습하려면 sparse checkout 범위를 확장합니다.

```bash
git sparse-checkout add 'kr/상법/*'
git sparse-checkout add 'kr/형법/*'
```

파일이 많은 주제를 한꺼번에 추가하면 checkout 시간이 늘어날 수 있습니다.

## 주의점

- 원본 README가 force-push 가능성을 명시합니다. commit hash를 장기 문서의 영구 식별자로만 쓰지 마세요.
- 법령 데이터는 공공저작물이지만 저장소 구조와 메타데이터는 MIT 라이선스입니다.
- 현재 checkout은 대표 법령 중심입니다. 전체 법령 검색이 필요하면 sparse 범위를 늘리거나 전체 checkout을 사용해야 합니다.
