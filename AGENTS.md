# AGENTS.md — korean-law-mcp-lab

기본 언어는 한국어다. AI 세션(Hermes, 또는 Hermes가 맡긴 Codex·Claude)은 이 파일과 [README.md](README.md)를 먼저 읽는다. 이 저장소는 법령 데이터와 MCP 실습 공간이며 **공개 저장소**다.

## 경계

- 결과물은 개발·리서치 실습용이다. 법률 자문처럼 단정하지 않는다.
- `LAW_OC`와 다른 비밀값은 열거나 출력하거나 커밋하지 않는다. 공개 저장소이므로 개인 정보와 내부 경로도 넣지 않는다.
- 실제 법제처 API 호출, 인증 시험, 중앙 Knowledge 등록은 별도 owner 승인 전에 하지 않는다.
- `upstreams/`의 원본 clone을 커밋하지 않고, `upstreams.lock.json`의 SHA만 쓴다. 기존 tracked `exports/`의 고정 경로 3개를 임의로 갱신하지 않는다.
- 이 장비의 8765 포트는 다른 서비스가 쓴다. MCP HTTP 시험은 다른 포트(예: 18765)로 하고, 그 서비스에 요청을 보내지 않는다.

## 검증과 병합

CI가 없다. PR 전에 `./scripts/verify.sh`와 `git diff --check`를 돌리고 결과를 PR에 적는다. 합성 자료와 임시 출력만 쓴다. 변경은 작업 브랜치와 PR로 하고, 로컬 시험 통과와 Claude 최종 검토를 근거로 Hermes가 병합한다.
