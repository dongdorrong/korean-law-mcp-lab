"""순수 메모리 법률 근거 계약. upstream 실행·네트워크·파일 쓰기 없음.

지원 승격 전 후보 계약이며 실제 live 결과를 생성하거나 검증하지 않는다.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import re

CONTRACT = "korean-law-evidence.dry-run.v1"
KINDS = {"snapshot", "live", "user_provided"}


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise ValueError("timezone-aware timestamp required")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("ISO calendar date required")
    return date.fromisoformat(value).isoformat()


def _evidence(document, kind, as_of, stale_after_days):
    if not isinstance(document, dict):
        raise ValueError("evidence document must be an object")
    doc = deepcopy(document)
    for key in ("document_id", "body", "uri", "content_hash"):
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            raise ValueError(f"{key}: nonempty string required")
    digest = "sha256:" + hashlib.sha256(doc["body"].encode("utf-8")).hexdigest()
    if digest != doc["content_hash"]:
        raise ValueError("evidence body hash mismatch")
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        raise ValueError("metadata: object required")
    if kind == "snapshot" and meta.get("evidence_kind") != "snapshot":
        raise ValueError("snapshot input must explicitly identify snapshot provenance")
    # User materials never inherit live/snapshot trust labels from their metadata.
    citation = {key: meta.get(key) for key in (
        "law_title", "law_type", "law_id", "article_no", "section_identity", "source_path",
        "identity_strength")}
    for key in ("law_title", "law_type", "article_no", "section_identity"):
        if not isinstance(citation[key], str) or not citation[key].strip():
            raise ValueError(f"citation {key}: nonempty string required")
    for key in ("law_id", "source_path", "identity_strength"):
        if citation[key] is not None and not isinstance(citation[key], str):
            raise ValueError(f"citation {key}: string or null required")
    citation.update(uri=doc["uri"], document_id=doc["document_id"], revision=digest)
    promulgation = _date(meta.get("promulgation_date"))
    enforcement = _date(meta.get("enforcement_date"))
    source_modified = meta.get("source_modified_at")
    if source_modified is not None:
        _timestamp(source_modified)
    upstream_commit = meta.get("upstream_commit") if kind == "snapshot" else None
    if upstream_commit is not None and (not isinstance(upstream_commit, str) or not re.fullmatch(
            r"[a-fA-F0-9]{40}", upstream_commit)):
        raise ValueError("upstream_commit: 40 hex characters or null required")
    observed = meta.get("observed_at")
    freshness, reason = "unknown", "no_observation_policy"
    if observed is None:
        reason = "observed_at_missing"
    else:
        age = _timestamp(as_of) - _timestamp(observed)
        if age < timedelta(0):
            reason = "observation_in_future"
        elif stale_after_days is not None:
            if age > timedelta(days=stale_after_days):
                freshness, reason = "stale", "observation_age_exceeds_policy"
            else:
                reason = "within_observation_window_latestness_unverified"
    return {
        "evidence_kind": kind,
        "source": {"kind": "local_snapshot" if kind == "snapshot" else "user_supplied",
                   "reference": doc["uri"],
                   "upstream_commit": upstream_commit},
        "text": doc["body"], "citation": citation,
        "observed_at": observed, "source_modified_at": source_modified,
        "promulgation_date": promulgation, "enforcement_date": enforcement,
        "temporal_relation": "unknown" if enforcement is None else (
            "future_enforcement_date" if date.fromisoformat(enforcement) > _timestamp(as_of).astimezone(
                timezone(timedelta(hours=9))).date()
            else "date_not_future"),
        "freshness_status": freshness, "freshness_reason": reason,
        "live_verified": False, "live_verified_at": None,
        "live_validation_status": "not_tested_owner_key_required",
        "legal_effect_status": "not_determined", "amendment_status": "not_determined",
        "supersession_status": "not_determined", "legal_advice": False,
        "human_review_required": True,
    }


def preview(*, requested_kind, as_of, snapshot_documents=(), user_documents=(), stale_after_days=None):
    """명시한 종류만 반환. live 요청은 항상 미검증 차단, snapshot 대체 금지.

    사용자 자료는 별도 인수로만 수신하며 같은 조문의 상이한 내용/날짜는
    충돌로 보존한다. 가장 늦은 관측·공포·시행일로 승자를 고르지 않는다.
    """
    if requested_kind not in KINDS | {"all_offline"}:
        raise ValueError("unsupported evidence kind")
    _timestamp(as_of)
    if stale_after_days is not None and (type(stale_after_days) is not int or
                                       not 0 <= stale_after_days <= timedelta.max.days):
        raise ValueError(f"stale_after_days must be an integer in 0..{timedelta.max.days} or null")
    response = {
        "contract": CONTRACT, "dry_run": True, "promotion_status": "deferred_owner_review",
        "requested_kind": requested_kind, "as_of": as_of,
        "stale_after_days": stale_after_days, "status": "evidence_preview",
        "live_verified": False, "live_validation_status": "not_tested_owner_key_required",
        "legal_advice": False, "human_review_required": True,
        "capabilities": {"network": False, "file_writes": False, "central_writes": False,
                         "filing": False, "submission": False, "account_actions": False},
        "limitations": ["최신 법령·실제 효력 미확인. 원문과 전문가 검토가 필요합니다.",
                        "LAW_OC 실시간 인증·호출 한도·오류 동작 미검증."],
        "evidence": [],
    }
    if requested_kind == "live":
        response["status"] = "live_validation_required"
        return response
    evidence = []
    if requested_kind in {"snapshot", "all_offline"}:
        evidence.extend(_evidence(doc, "snapshot", as_of, stale_after_days) for doc in snapshot_documents)
    if requested_kind in {"user_provided", "all_offline"}:
        evidence.extend(_evidence(doc, "user_provided", as_of, stale_after_days) for doc in user_documents)
    groups = {}
    for item in evidence:
        cite = item["citation"]
        # Without official identity, titles alone cannot establish source conflict.
        key = ((cite["law_id"], cite["law_type"], cite["section_identity"], cite["article_no"])
               if cite["law_id"] else (item["evidence_kind"], cite["document_id"]))
        groups.setdefault(key, []).append(item)
    for items in groups.values():
        versions = {(i["citation"]["revision"], i["promulgation_date"], i["enforcement_date"]) for i in items}
        if len(versions) > 1:
            for item in items:
                item["freshness_status"] = "conflicting"
                item["freshness_reason"] = "same_identity_different_content_or_dates"
    response["evidence"] = sorted(evidence, key=lambda i: (
        i["citation"]["document_id"], i["evidence_kind"], i["source"]["reference"], i["citation"]["revision"]))
    if not evidence:
        response["status"] = "no_evidence"
    return response
