# Korean Law MCP Lab

읽기 전용 한국 법령 **snapshot evidence/export 실습** 저장소입니다. 법률 자문, 현재 유효 법령의 확정, 사건 판단, 제출·계정 작업을 제공하지 않습니다. Live API는 exporter에서 호출하지 않습니다.

## 재현 가능한 offline 검증

```bash
./scripts/verify.sh
```

검증은 합성 fixture와 임시 디렉터리만 사용합니다. 기존 `exports/`나 실제 upstream checkout을 갱신하지 않습니다.

## Upstream 준비와 업데이트 제안

`upstreams.lock.json`의 commit을 사용합니다. 기존 checkout이 dirty/remote 불일치/다른 HEAD면 중단하며 자동 덮어쓰지 않습니다. 사라진 commit을 현재 HEAD로 대체하지 않습니다.

```bash
./scripts/bootstrap-upstreams.sh              # 잠긴 commit 준비 (네트워크 필요)
./scripts/bootstrap-upstreams.sh --propose-update # 후보 HEAD 출력만
```

업데이트 후보는 license·provenance·fixture 호환성을 별도로 검토하고 lock을 변경해야 합니다. `legalize-kr` 라이선스는 아직 확인되지 않아 재배포 승인이 아닙니다. 공개 upstream의 현재 HEAD는 검증된 lock으로 자동 승격되지 않습니다.

## 로컬 export

기본 입력은 `upstreams/legalize-kr/kr`이며 고정 산출물은 JSONL, SQLite, manifest입니다. 실데이터를 건드리지 않는 실행 예시는 `scripts/verify.sh`의 합성 fixture를 참조하십시오. 수동 실행 시 `--root`, `--source-dir`, `--jsonl`, `--sqlite`, `--manifest` 모두 전용 임시 디렉터리를 지정하며, 산출물은 `--root` 내부여야 합니다. 기본 0건은 기존 export를 보존하며, `--allow-empty`만 명시적으로 빈 결과를 허용합니다. `--limit`은 smoke용 partial로 표시됩니다. 생성물은 manifest 마지막 교체 + checksum 검증 방식이며, 고정 경로 소비자는 `verify_published()` 또는 동등 검증을 먼저 해야 합니다. 검증 없이 파일을 직접 읽는 구 소비자는 중단 시 혼합 세대를 볼 수 있습니다.

`--migration-report <path>`는 기존 ordinal ID와 새 논리 ID의 **dry-run** mapping만 작성합니다. 기존 DB·중앙 자료는 변경하지 않습니다. 날짜는 공포일·시행일·관측 시각을 분리하며, API를 호출하지 않은 snapshot은 항상 unverified입니다. LAW_OC 설정은 인증/검색 성공이 아닙니다.

기존 tracked `exports/`는 이전 버전 산출물이며 이번 작업에서 다시 생성하거나 갱신하지 않았습니다. 새 계약 검증 결과로 간주하지 말고, 격리된 새 export와 migration report를 검토하십시오.

중앙 Knowledge v1은 현재 `source_id=korean-law-mcp-lab`을 허용하지 않습니다. `scripts/reconcile_knowledge_contract.py <jsonl>`은 offline 거절 보고만 합니다. 등록·live 검증·지원 adapter 승격은 별도 소유권/승인 gate입니다. 자세한 범위는 `docs/completion-ledger.md`, `docs/fordongdorrong-integration.md`를 보십시오.
