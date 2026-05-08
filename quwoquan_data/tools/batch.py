from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import (
    BATCH_LOOP_STATE_SCHEMA_VERSION,
    RETRIEVAL_PLAN_SCHEMA_VERSION,
    SUPPORTED_CONTENT_TYPES,
    SUPPORTED_SEARCH_PROVIDERS,
    SUPPORTED_TARGETS,
    batch_plan_path_from_arg,
    content_template_for_ref,
    entity_name_for_ref,
    entity_payload_for_ref,
    load_user_pool,
    loop_state_path,
    now_iso,
    out_batch_dir,
    publish_batch_dir,
    raw_batch_dir,
    raw_batch_file,
    read_json,
    read_ndjson,
    read_yaml,
    ref_exists,
    retrieval_plan_path,
    tag_id_for_ref,
    tag_label_for_ref,
    write_json,
    write_ndjson,
    write_text,
)
from retrieval_contract import (
    build_retrieval_prompt,
    default_location_search_name,
    search_query_item,
)


def _required_string(plan: dict[str, Any], field: str, errors: list[str]) -> None:
    value = plan.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"batch_plan 缺少 {field}")


def _required_string_list(plan: dict[str, Any], field: str, errors: list[str]) -> None:
    value = plan.get(field)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        errors.append(f"batch_plan 的 {field} 必须是非空字符串数组")


def _required_int(plan: dict[str, Any], field: str, errors: list[str]) -> None:
    value = plan.get(field)
    if not isinstance(value, int) or value < 1:
        errors.append(f"batch_plan 的 {field} 必须是 >= 1 的整数")


def completion_policy(plan: dict[str, Any]) -> dict[str, int]:
    payload = dict(plan.get("completion_policy", {}))
    return {
        "min_fact_count": int(payload.get("min_fact_count", 1)),
        "min_evidence_urls": int(payload.get("min_evidence_urls", 1)),
        "min_perspective_count": int(payload.get("min_perspective_count", 1)),
        "no_new_query_stop_rounds": int(payload.get("no_new_query_stop_rounds", 1)),
    }


def retrieval_context(plan: dict[str, Any]) -> dict[str, str]:
    payload = dict(plan.get("retrieval_context", {}))
    location = str(payload.get("location", "")).strip()
    if not location and plan.get("entity_refs"):
        first_entity = entity_payload_for_ref(str(plan["entity_refs"][0]))
        location = str(first_entity.get("city", "")).strip()
    location_search_name = str(payload.get("location_search_name", "")).strip()
    if location and not location_search_name:
        location_search_name = default_location_search_name(location)
    return {
        "location": location,
        "location_search_name": location_search_name,
    }


def validate_batch_plan(plan: dict[str, Any], selected_targets: list[str]) -> list[str]:
    errors: list[str] = []
    for field in ("batch_id", "query", "search_provider", "content_type_ref"):
        _required_string(plan, field, errors)
    for field in ("allow_domains", "creator_refs", "entity_refs", "tag_refs", "target_envs"):
        _required_string_list(plan, field, errors)
    for field in ("fetch_top_k", "expansion_rounds"):
        _required_int(plan, field, errors)
    if not isinstance(plan.get("publish_policy"), dict):
        errors.append("batch_plan 缺少 publish_policy")
    if errors:
        return errors

    search_provider = str(plan["search_provider"]).strip()
    if search_provider not in SUPPORTED_SEARCH_PROVIDERS:
        errors.append(
            f"search_provider 只支持 {', '.join(sorted(SUPPORTED_SEARCH_PROVIDERS))}，收到 {search_provider}"
        )
    target_set = set(plan.get("target_envs", [])) | set(selected_targets)
    invalid_targets = sorted(target_set - SUPPORTED_TARGETS)
    if invalid_targets:
        errors.append(f"target_envs 非法: {', '.join(invalid_targets)}")

    template_ref = str(plan["content_type_ref"])
    if not ref_exists(template_ref):
        errors.append(f"content_type_ref 不存在: {template_ref}")
    else:
        template = content_template_for_ref(template_ref)
        if template.get("content_type") not in SUPPORTED_CONTENT_TYPES:
            errors.append(
                f"当前 batch run 仅支持 image/article，收到 {template.get('content_type')}"
            )

    user_pool = load_user_pool()
    for user_id in plan.get("creator_refs", []):
        if user_id not in user_pool:
            errors.append(f"creator_refs 不存在于 user_pool: {user_id}")
    for ref in plan.get("entity_refs", []):
        if not ref_exists(ref):
            errors.append(f"entity_refs 引用不存在: {ref}")
    for ref in plan.get("tag_refs", []):
        if not ref_exists(ref):
            errors.append(f"tag_refs 引用不存在: {ref}")

    for key, value in completion_policy(plan).items():
        if value < 1:
            errors.append(f"completion_policy.{key} 必须 >= 1")
    return errors


def ensure_raw_skeleton(batch_id: str) -> None:
    raw_dir = raw_batch_dir(batch_id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in ("search_results.ndjson", "pages.ndjson", "assets.ndjson", "facts.ndjson"):
        path = raw_batch_file(batch_id, name)
        if not path.exists():
            write_text(path, "")


def load_loop_state(batch_id: str) -> dict[str, Any]:
    path = loop_state_path(batch_id)
    if path.exists():
        return dict(read_json(path))
    return {
        "schemaVersion": BATCH_LOOP_STATE_SCHEMA_VERSION,
        "batch_id": batch_id,
        "current_round": 0,
        "last_planned_round": 0,
        "status": "needs_more_evidence",
        "completed": False,
        "ready_for_finalize": False,
        "stop_reason": "",
        "rounds_without_new_queries": 0,
        "missing_entity_refs": [],
        "missing_tag_refs": [],
        "next_queries": [],
        "summary": {
            "search_result_count": 0,
            "page_count": 0,
            "asset_count": 0,
            "fact_count": 0,
            "perspective_count": 0,
            "evidence_url_count": 0,
        },
    }


def load_retrieval_plan(batch_id: str) -> dict[str, Any]:
    path = retrieval_plan_path(batch_id)
    if path.exists():
        return dict(read_json(path))
    return {}


def load_raw_state(batch_id: str) -> dict[str, Any]:
    return {
        "search_results": read_ndjson(raw_batch_file(batch_id, "search_results.ndjson")),
        "pages": read_ndjson(raw_batch_file(batch_id, "pages.ndjson")),
        "assets": read_ndjson(raw_batch_file(batch_id, "assets.ndjson")),
        "facts": read_ndjson(raw_batch_file(batch_id, "facts.ndjson")),
        "loop_state": load_loop_state(batch_id),
        "retrieval_plan": load_retrieval_plan(batch_id),
    }


def int_round(value: Any) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def max_round_in_rows(rows: list[dict[str, Any]]) -> int:
    rounds = [int_round(row.get("round")) for row in rows]
    return max(rounds, default=0)


def normalize_domain(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def round_list(batch_state: dict[str, Any]) -> list[int]:
    values = [
        max_round_in_rows(batch_state["search_results"]),
        max_round_in_rows(batch_state["pages"]),
        max_round_in_rows(batch_state["assets"]),
        max_round_in_rows(batch_state["facts"]),
        int_round(batch_state["loop_state"].get("current_round")),
    ]
    return [value for value in values if value > 0]


def distinct_domains(rows: list[dict[str, Any]], facts: list[dict[str, Any]]) -> set[str]:
    domains = {
        normalize_domain(str(row.get("domain", "")))
        for row in rows
        if normalize_domain(str(row.get("domain", "")))
    }
    for row in facts:
        parsed = urlparse(str(row.get("source_url", "")).strip())
        if parsed.netloc:
            domains.add(normalize_domain(parsed.netloc))
    return domains


def distinct_evidence_urls(batch_state: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for key in ("search_results", "pages", "facts"):
        for row in batch_state[key]:
            for field in ("url", "source_url"):
                value = str(row.get(field, "")).strip()
                if value:
                    urls.add(value)
    return urls


def covered_entity_refs(facts: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for row in facts:
        covered.update(str(item).strip() for item in row.get("entity_refs", []) if str(item).strip())
    return covered


def covered_tag_refs(facts: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for row in facts:
        covered.update(str(item).strip() for item in row.get("tag_refs", []) if str(item).strip())
    return covered


def compute_batch_status(plan: dict[str, Any], batch_state: dict[str, Any]) -> dict[str, Any]:
    policy = completion_policy(plan)
    loop_state = batch_state["loop_state"]
    retrieval_plan = batch_state["retrieval_plan"]
    current_round = max(round_list(batch_state), default=0)
    last_planned_round = max(current_round, int_round(loop_state.get("last_planned_round")))
    if retrieval_plan:
        last_planned_round = max(last_planned_round, int_round(retrieval_plan.get("round")))

    facts = batch_state["facts"]
    missing_entities = sorted(set(plan["entity_refs"]) - covered_entity_refs(facts))
    missing_tags = sorted(set(plan["tag_refs"]) - covered_tag_refs(facts))
    fact_count = len(facts)
    evidence_url_count = len(distinct_evidence_urls(batch_state))
    perspective_count = len(distinct_domains(batch_state["search_results"], facts))
    required_files_present = all(
        raw_batch_file(plan["batch_id"], name).exists()
        for name in ("search_results.ndjson", "pages.ndjson", "assets.ndjson", "facts.ndjson", "loop_state.json")
    )

    can_finalize = (
        required_files_present
        and not missing_entities
        and not missing_tags
        and fact_count >= policy["min_fact_count"]
        and evidence_url_count >= policy["min_evidence_urls"]
        and perspective_count >= policy["min_perspective_count"]
    )
    completed = bool(loop_state.get("completed"))
    next_queries = []
    if isinstance(retrieval_plan.get("search_queries"), list):
        next_queries = [
            str(item.get("query", "")).strip()
            for item in retrieval_plan["search_queries"]
            if isinstance(item, dict) and str(item.get("query", "")).strip()
        ]
    awaiting_collection = bool(next_queries) and int_round(retrieval_plan.get("round")) > current_round
    exhausted = (
        not can_finalize
        and not completed
        and (
            current_round >= int(plan["expansion_rounds"])
            or int_round(loop_state.get("rounds_without_new_queries"))
            >= policy["no_new_query_stop_rounds"]
        )
    )

    if completed:
        status = "completed"
    elif can_finalize:
        status = "ready_for_finalize"
    elif awaiting_collection:
        status = "awaiting_collection"
    elif exhausted:
        status = "exhausted"
    else:
        status = "needs_more_evidence"

    return {
        "batch_id": plan["batch_id"],
        "search_provider": plan["search_provider"],
        "current_round": current_round,
        "last_planned_round": last_planned_round,
        "remaining_rounds": max(int(plan["expansion_rounds"]) - current_round, 0),
        "status": status,
        "completed": completed,
        "ready_for_finalize": can_finalize,
        "can_finalize": can_finalize,
        "search_result_count": len(batch_state["search_results"]),
        "page_count": len(batch_state["pages"]),
        "asset_count": len(batch_state["assets"]),
        "fact_count": fact_count,
        "evidence_url_count": evidence_url_count,
        "perspective_count": perspective_count,
        "required_entity_count": len(plan["entity_refs"]),
        "covered_entity_count": len(set(plan["entity_refs"]) - set(missing_entities)),
        "missing_entity_refs": missing_entities,
        "required_tag_count": len(plan["tag_refs"]),
        "covered_tag_count": len(set(plan["tag_refs"]) - set(missing_tags)),
        "missing_tag_refs": missing_tags,
        "next_queries_count": len(next_queries),
        "next_queries": next_queries,
        "rounds_without_new_queries": int_round(loop_state.get("rounds_without_new_queries")),
        "stop_reason": str(loop_state.get("stop_reason", "")).strip(),
        "completion_policy": policy,
    }


def build_search_queries(plan: dict[str, Any], status: dict[str, Any], next_round: int) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    target_domains = list(plan["allow_domains"])
    seen: set[str] = set()

    def add_query(
        *,
        dimension: str,
        query: str,
        purpose: str,
        entity_refs: list[str] | None = None,
        tag_refs: list[str] | None = None,
    ) -> None:
        normalized = query.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        queries.append(
            search_query_item(
                dimension=dimension,
                query=normalized,
                purpose=purpose,
                round_number=next_round,
                target_domains=target_domains,
                entity_refs=entity_refs,
                tag_refs=tag_refs,
            )
        )

    add_query(
        dimension="主检索",
        query=str(plan["query"]),
        purpose="围绕批次主主题补齐公开网页证据，并为本轮事实抽取提供总入口。",
    )

    for ref in status["missing_entity_refs"]:
        name = entity_name_for_ref(ref)
        add_query(
            dimension="实体补齐",
            query=f"{name} {plan['query']}",
            purpose=f"补齐缺失实体「{name}」的公开证据与内容上下文。",
            entity_refs=[ref],
        )

    for ref in status["missing_tag_refs"]:
        label = tag_label_for_ref(ref)
        add_query(
            dimension="标签视角",
            query=f"{plan['query']} {label}",
            purpose=f"补齐缺失标签「{label}」对应的内容视角与叙事线索。",
            tag_refs=[ref],
        )

    if status["fact_count"] < status["completion_policy"]["min_fact_count"]:
        template = content_template_for_ref(plan["content_type_ref"])
        focus = "游记 攻略" if template["content_type"] == "article" else "打卡 出片"
        add_query(
            dimension="内容增量",
            query=f"{plan['query']} {focus}",
            purpose="当前事实条数不足，补齐可生成内容的多视角样本。",
        )

    if status["perspective_count"] < status["completion_policy"]["min_perspective_count"]:
        add_query(
            dimension="来源扩展",
            query=f"{plan['query']} 不同来源 对比",
            purpose="当前来源视角不足，补齐不同站点或不同写法的可核验证据。",
        )

    return queries


def build_retrieval_plan(plan: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    next_round = max(status["current_round"] + 1, 1)
    context = retrieval_context(plan)
    search_queries: list[dict[str, Any]] = []
    stop_reason = ""

    if status["completed"]:
        plan_status = "completed"
    elif status["can_finalize"]:
        plan_status = "ready_for_finalize"
    else:
        search_queries = build_search_queries(plan, status, next_round)
        if not search_queries and (
            status["current_round"] >= int(plan["expansion_rounds"])
            or status["rounds_without_new_queries"]
            >= status["completion_policy"]["no_new_query_stop_rounds"]
        ):
            plan_status = "exhausted"
            stop_reason = "no_high_value_query"
        else:
            plan_status = "planned"

    planner_prompt = build_retrieval_prompt(
        batch_id=plan["batch_id"],
        main_query=str(plan["query"]),
        next_round=next_round,
        location=context["location"],
        location_search_name=context["location_search_name"],
        target_domains=list(plan["allow_domains"]),
        missing_entity_refs=list(status["missing_entity_refs"]),
        missing_tag_refs=list(status["missing_tag_refs"]),
        fact_count=int(status["fact_count"]),
    )

    return {
        "schemaVersion": RETRIEVAL_PLAN_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "batch_id": plan["batch_id"],
        "round": next_round,
        "status": plan_status,
        "query": str(plan["query"]),
        "search_queries": search_queries,
        "location": context["location"],
        "location_search_name": context["location_search_name"],
        "target_domains": list(plan["allow_domains"]),
        "missing_entity_refs": list(status["missing_entity_refs"]),
        "missing_tag_refs": list(status["missing_tag_refs"]),
        "planner_prompt": planner_prompt,
        "stop_reason": stop_reason,
    }


def write_loop_state(
    plan: dict[str, Any],
    status: dict[str, Any],
    retrieval_plan: dict[str, Any],
) -> dict[str, Any]:
    previous = load_loop_state(plan["batch_id"])
    if retrieval_plan["status"] == "completed":
        loop_status = "completed"
        stop_reason = "dry_run_passed"
        rounds_without_new_queries = 0
    elif retrieval_plan["status"] == "ready_for_finalize":
        loop_status = "ready_for_finalize"
        stop_reason = ""
        rounds_without_new_queries = 0
    elif retrieval_plan["status"] == "exhausted":
        loop_status = "exhausted"
        stop_reason = retrieval_plan.get("stop_reason") or "max_rounds_reached"
        rounds_without_new_queries = int(previous.get("rounds_without_new_queries", 0)) + 1
    elif retrieval_plan["search_queries"]:
        loop_status = "awaiting_collection"
        stop_reason = ""
        rounds_without_new_queries = 0
    else:
        loop_status = "needs_more_evidence"
        stop_reason = ""
        rounds_without_new_queries = int(previous.get("rounds_without_new_queries", 0)) + 1

    payload = {
        "schemaVersion": BATCH_LOOP_STATE_SCHEMA_VERSION,
        "batch_id": plan["batch_id"],
        "current_round": int(status["current_round"]),
        "last_planned_round": int(retrieval_plan["round"]),
        "status": loop_status,
        "completed": loop_status == "completed",
        "ready_for_finalize": loop_status in {"ready_for_finalize", "completed"},
        "stop_reason": stop_reason,
        "rounds_without_new_queries": rounds_without_new_queries,
        "missing_entity_refs": list(status["missing_entity_refs"]),
        "missing_tag_refs": list(status["missing_tag_refs"]),
        "next_queries": [item["query"] for item in retrieval_plan["search_queries"]],
        "summary": {
            "search_result_count": int(status["search_result_count"]),
            "page_count": int(status["page_count"]),
            "asset_count": int(status["asset_count"]),
            "fact_count": int(status["fact_count"]),
            "perspective_count": int(status["perspective_count"]),
            "evidence_url_count": int(status["evidence_url_count"]),
        },
    }
    write_json(loop_state_path(plan["batch_id"]), payload)
    return payload


def validate_search_results(batch_id: str, rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return [f"raw/{batch_id}/search_results.ndjson 至少需要 1 条 search_result"]
    for row in rows:
        ref = row.get("url") or row.get("title") or "<unknown>"
        for field in ("query", "domain", "url", "title", "snippet", "collector"):
            if not str(row.get(field, "")).strip():
                errors.append(f"search_result {ref} 缺少 {field}")
        if int_round(row.get("round")) < 1:
            errors.append(f"search_result {ref} 的 round 必须 >= 1")
    return errors


def validate_pages(batch_id: str, rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return [f"raw/{batch_id}/pages.ndjson 至少需要 1 条 page"]
    for row in rows:
        ref = row.get("url") or row.get("title") or "<unknown>"
        for field in ("url", "title", "plain_text", "fetched_at", "evidence_hash"):
            if not str(row.get(field, "")).strip():
                errors.append(f"page {ref} 缺少 {field}")
        if int_round(row.get("round")) < 1:
            errors.append(f"page {ref} 的 round 必须 >= 1")
    return errors


def validate_assets(batch_id: str, rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for row in rows:
        ref = row.get("asset_id") or "<unknown>"
        for field in ("asset_id", "object_key", "source_url", "caption"):
            if not str(row.get(field, "")).strip():
                errors.append(f"asset {ref} 缺少 {field}")
        if int_round(row.get("round")) < 1:
            errors.append(f"asset {ref} 的 round 必须 >= 1")
    return errors


def validate_facts(batch_id: str, rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return [f"raw/{batch_id}/facts.ndjson 至少需要 1 条 fact"]
    for row in rows:
        fact_id = row.get("fact_id") or "<unknown>"
        if not str(row.get("title", "")).strip():
            errors.append(f"fact {fact_id} 缺少 title")
        if not str(row.get("source_url", "")).strip():
            errors.append(f"fact {fact_id} 缺少 source_url")
        if not isinstance(row.get("entity_refs"), list) or not row["entity_refs"]:
            errors.append(f"fact {fact_id} 缺少 entity_refs")
        if not isinstance(row.get("tag_refs"), list) or not row["tag_refs"]:
            errors.append(f"fact {fact_id} 缺少 tag_refs")
        if int_round(row.get("round")) < 1:
            errors.append(f"fact {fact_id} 的 round 必须 >= 1")
    return errors


def validate_loop_state(batch_id: str, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_fields = (
        "current_round",
        "last_planned_round",
        "status",
        "completed",
        "ready_for_finalize",
        "stop_reason",
        "rounds_without_new_queries",
        "missing_entity_refs",
        "missing_tag_refs",
        "next_queries",
    )
    for field in required_fields:
        if field not in payload:
            errors.append(f"raw/{batch_id}/loop_state.json 缺少 {field}")
    return errors


def validate_raw_inputs(plan: dict[str, Any], batch_state: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    batch_id = plan["batch_id"]
    errors: list[str] = []
    required_files = (
        "search_results.ndjson",
        "pages.ndjson",
        "assets.ndjson",
        "facts.ndjson",
        "loop_state.json",
    )
    for name in required_files:
        if not raw_batch_file(batch_id, name).exists():
            errors.append(f"raw/{batch_id}/{name} 不存在")
    errors.extend(validate_search_results(batch_id, batch_state["search_results"]))
    errors.extend(validate_pages(batch_id, batch_state["pages"]))
    errors.extend(validate_assets(batch_id, batch_state["assets"]))
    errors.extend(validate_facts(batch_id, batch_state["facts"]))
    errors.extend(validate_loop_state(batch_id, batch_state["loop_state"]))
    status = compute_batch_status(plan, batch_state)
    return errors, status


def _asset_map(batch_id: str) -> dict[str, dict[str, Any]]:
    rows = read_ndjson(raw_batch_file(batch_id, "assets.ndjson"))
    return {str(row["asset_id"]): row for row in rows if row.get("asset_id")}


def _normalize_cover_url(fact: dict[str, Any], assets: dict[str, dict[str, Any]]) -> str:
    for field in ("cover_asset_id",):
        asset_id = str(fact.get(field, "")).strip()
        if asset_id and asset_id in assets:
            return str(assets[asset_id]["object_key"])
    for field in ("media_asset_ids", "figure_asset_ids"):
        for asset_id in fact.get(field, []):
            asset_key = str(asset_id).strip()
            if asset_key in assets:
                return str(assets[asset_key]["object_key"])
    return ""


def _tag_ids(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ref in refs:
        tag_id = tag_id_for_ref(ref)
        if tag_id in seen:
            continue
        seen.add(tag_id)
        result.append(tag_id)
    return result


def build_entities(plan: dict[str, Any], search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_urls = [row["url"] for row in search_results if row.get("url")]
    entities: list[dict[str, Any]] = []
    for ref in plan["entity_refs"]:
        payload = entity_payload_for_ref(ref)
        payload["evidence_refs"] = list(
            dict.fromkeys(list(payload.get("evidence_refs", [])) + evidence_urls[:5])
        )
        entities.append(payload)
    return entities


def build_image_payload(
    batch_id: str,
    index: int,
    fact: dict[str, Any],
    template: dict[str, Any],
    author: dict[str, str],
    assets: dict[str, dict[str, Any]],
    all_tag_refs: list[str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    media_urls = [
        str(assets[asset_id]["object_key"])
        for asset_id in fact.get("media_asset_ids", [])
        if asset_id in assets
    ]
    cover_url = _normalize_cover_url(fact, assets)
    return {
        "post_payload": {
            "contentType": template["content_type"],
            "type": template["content_type"],
            "contentIdentity": template["content_identity"],
            "title": fact["title"],
            "summary": fact.get("summary", ""),
            "body": fact.get("body", ""),
            "mediaUrls": media_urls,
            "coverUrl": cover_url,
            "tags": _tag_ids(all_tag_refs),
            "locationName": fact.get("location_name", ""),
            "width": fact.get("width"),
            "height": fact.get("height"),
            "visibility": policy.get("visibility", "public"),
            "assistantUsePolicy": policy.get("assistant_use_policy", "inherit"),
            "authorId": author["userId"],
            "authorDisplayNameSnapshot": author["displayName"],
            "authorAvatarUrlSnapshot": author["avatarObjectKey"],
            "sourceType": "cold_start_batch",
            "sourcePostId": f"{batch_id}_image_{index:03d}",
        },
        "semantic": {
            "entity_refs": fact.get("entity_refs", []),
            "tag_refs": all_tag_refs,
            "source_urls": [fact["source_url"]],
        },
    }


def build_article_document(fact: dict[str, Any], assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cover_url = _normalize_cover_url(fact, assets)
    nodes: list[dict[str, Any]] = [{"id": "title", "type": "documentTitle", "text": fact["title"]}]
    for index, paragraph in enumerate(fact.get("article_paragraphs", []), start=1):
        nodes.append({"id": f"paragraph_{index}", "type": "paragraph", "text": paragraph})
    for index, asset_id in enumerate(fact.get("figure_asset_ids", []), start=1):
        asset = assets.get(asset_id)
        if not asset:
            continue
        nodes.append(
            {
                "id": f"figure_{index}",
                "type": "figure",
                "imageUrl": asset["object_key"],
                "imageLayout": "fullWidth",
                "caption": asset.get("caption", ""),
            }
        )
    return {
        "template": fact.get("article_template", "journal"),
        "fontPreset": fact.get("article_font_preset", "clean"),
        "coverImageUrl": cover_url,
        "titleStyle": "major",
        "nodes": nodes,
    }


def build_article_payload(
    batch_id: str,
    index: int,
    fact: dict[str, Any],
    template: dict[str, Any],
    author: dict[str, str],
    assets: dict[str, dict[str, Any]],
    all_tag_refs: list[str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    cover_url = _normalize_cover_url(fact, assets)
    return {
        "post_payload": {
            "contentType": template["content_type"],
            "type": template["content_type"],
            "contentIdentity": template["content_identity"],
            "title": fact["title"],
            "summary": fact.get("summary", ""),
            "coverUrl": cover_url,
            "tags": _tag_ids(all_tag_refs),
            "locationName": fact.get("location_name", ""),
            "visibility": policy.get("visibility", "public"),
            "assistantUsePolicy": policy.get("assistant_use_policy", "inherit"),
            "authorId": author["userId"],
            "authorDisplayNameSnapshot": author["displayName"],
            "authorAvatarUrlSnapshot": author["avatarObjectKey"],
            "sourceType": "cold_start_batch",
            "sourcePostId": f"{batch_id}_article_{index:03d}",
            "articleDocument": build_article_document(fact, assets),
        },
        "semantic": {
            "entity_refs": fact.get("entity_refs", []),
            "tag_refs": all_tag_refs,
            "source_urls": [fact["source_url"]],
        },
    }


def build_posts(plan: dict[str, Any], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    template = content_template_for_ref(plan["content_type_ref"])
    users = load_user_pool()
    assets = _asset_map(plan["batch_id"])
    policy = dict(plan.get("publish_policy", {}))
    posts: list[dict[str, Any]] = []
    for index, fact in enumerate(facts, start=1):
        author_id = plan["creator_refs"][(index - 1) % len(plan["creator_refs"])]
        author = users[author_id]
        all_tag_refs = list(dict.fromkeys(plan["tag_refs"] + fact.get("tag_refs", [])))
        if template["content_type"] == "image":
            posts.append(
                build_image_payload(
                    plan["batch_id"], index, fact, template, author, assets, all_tag_refs, policy
                )
            )
        elif template["content_type"] == "article":
            posts.append(
                build_article_payload(
                    plan["batch_id"], index, fact, template, author, assets, all_tag_refs, policy
                )
            )
    return posts


def write_publish_summary(
    batch_id: str,
    plan: dict[str, Any],
    entities: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> None:
    target_dir = publish_batch_dir(batch_id)
    titles = [row["post_payload"].get("title", "") for row in posts]
    lines = [
        f"# 发布摘要：{batch_id}",
        "",
        f"- query: `{plan['query']}`",
        f"- search_provider: `{plan['search_provider']}`",
        f"- content_type_ref: `{plan['content_type_ref']}`",
        f"- entities: {len(entities)}",
        f"- posts: {len(posts)}",
        f"- target_envs: {', '.join(plan['target_envs'])}",
        "",
    ]
    if titles:
        lines.append("## 生成内容")
        lines.append("")
        for title in titles:
            lines.append(f"- {title}")
        lines.append("")
    write_text(target_dir / "summary.md", "\n".join(lines).strip() + "\n")


def _projection_asset_refs(entities: list[dict[str, Any]], posts: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for entity in entities:
        refs.extend(entity.get("media_refs", []))
    for row in posts:
        payload = row["post_payload"]
        refs.extend(payload.get("mediaUrls", []))
        if payload.get("coverUrl"):
            refs.append(payload["coverUrl"])
        article_document = payload.get("articleDocument")
        if isinstance(article_document, dict):
            if article_document.get("coverImageUrl"):
                refs.append(article_document["coverImageUrl"])
            for node in article_document.get("nodes", []):
                image_url = node.get("imageUrl")
                if image_url:
                    refs.append(image_url)
    return list(dict.fromkeys(refs))


def write_projection(
    batch_id: str,
    target: str,
    plan: dict[str, Any],
    entities: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> None:
    target_dir = out_batch_dir(batch_id)
    payload = {
        "schemaVersion": "quwoquan_data.projection.v2",
        "generated_at": now_iso(),
        "environment": target,
        "batch_id": batch_id,
        "query": plan["query"],
        "content_type_ref": plan["content_type_ref"],
        "entity_ids": [row["entity_id"] for row in entities],
        "entity_refs": [row["entity_ref"] for row in entities],
        "post_titles": [row["post_payload"].get("title", "") for row in posts],
        "post_source_ids": [row["post_payload"].get("sourcePostId", "") for row in posts],
        "asset_refs": _projection_asset_refs(entities, posts),
        "scope": "dry_run",
        "dry_run_only": True,
    }
    write_json(target_dir / f"{target}_projection.json", payload)


def handle_plan_retrieval(args) -> int:
    plan_path = batch_plan_path_from_arg(args.plan)
    if not plan_path.exists():
        print(f"[batch plan-retrieval] FAIL: plan 不存在 {plan_path}", file=sys.stderr)
        return 1
    plan = read_yaml(plan_path)
    errors = validate_batch_plan(plan, list(plan.get("target_envs", [])))
    if errors:
        for error in errors:
            print(f"[batch plan-retrieval] FAIL: {error}", file=sys.stderr)
        return 1

    ensure_raw_skeleton(plan["batch_id"])
    batch_state = load_raw_state(plan["batch_id"])
    status = compute_batch_status(plan, batch_state)
    retrieval_plan = build_retrieval_plan(plan, status)
    write_json(retrieval_plan_path(plan["batch_id"]), retrieval_plan)
    loop_state = write_loop_state(plan, status, retrieval_plan)
    print(
        "[batch plan-retrieval] OK: "
        f"batch={plan['batch_id']} current_round={status['current_round']} "
        f"planned_round={retrieval_plan['round']} queries={len(retrieval_plan['search_queries'])} "
        f"status={loop_state['status']}"
    )
    return 0


def handle_status(args) -> int:
    plan_path = batch_plan_path_from_arg(args.plan)
    if not plan_path.exists():
        print(f"[batch status] FAIL: plan 不存在 {plan_path}", file=sys.stderr)
        return 1
    plan = read_yaml(plan_path)
    errors = validate_batch_plan(plan, list(plan.get("target_envs", [])))
    if errors:
        for error in errors:
            print(f"[batch status] FAIL: {error}", file=sys.stderr)
        return 1
    batch_state = load_raw_state(plan["batch_id"])
    status = compute_batch_status(plan, batch_state)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def handle_run(args) -> int:
    if not args.dry_run:
        print("[batch run] FAIL: 原型阶段只支持 --dry-run", file=sys.stderr)
        return 1
    plan_path = batch_plan_path_from_arg(args.plan)
    if not plan_path.exists():
        print(f"[batch run] FAIL: plan 不存在 {plan_path}", file=sys.stderr)
        return 1
    plan = read_yaml(plan_path)
    selected_targets = [
        item.strip() for item in str(args.targets or "").split(",") if item.strip()
    ] or list(plan.get("target_envs", []))
    errors = validate_batch_plan(plan, selected_targets)
    batch_state = load_raw_state(plan.get("batch_id", ""))
    raw_errors, status = validate_raw_inputs(plan, batch_state)
    errors.extend(raw_errors)
    if errors:
        for error in errors:
            print(f"[batch run] FAIL: {error}", file=sys.stderr)
        return 1
    if not status["can_finalize"] and not status["completed"]:
        print("[batch run] FAIL: 批次尚未满足 finalize 条件，请先补齐证据并执行 batch status", file=sys.stderr)
        return 1

    search_results = batch_state["search_results"]
    facts = batch_state["facts"]
    entities = build_entities(plan, search_results)
    posts = build_posts(plan, facts)
    publish_dir = publish_batch_dir(plan["batch_id"])
    write_ndjson(publish_dir / "entities.ndjson", entities)
    write_ndjson(publish_dir / "posts.ndjson", posts)
    write_publish_summary(plan["batch_id"], plan, entities, posts)
    for target in selected_targets:
        write_projection(plan["batch_id"], target, plan, entities, posts)

    loop_state = {
        **load_loop_state(plan["batch_id"]),
        "schemaVersion": BATCH_LOOP_STATE_SCHEMA_VERSION,
        "batch_id": plan["batch_id"],
        "current_round": int(status["current_round"]),
        "last_planned_round": max(
            int(status["last_planned_round"]), int(load_loop_state(plan["batch_id"]).get("last_planned_round", 0))
        ),
        "status": "completed",
        "completed": True,
        "ready_for_finalize": True,
        "stop_reason": "dry_run_passed",
        "rounds_without_new_queries": 0,
        "missing_entity_refs": [],
        "missing_tag_refs": [],
        "next_queries": [],
        "summary": {
            "search_result_count": int(status["search_result_count"]),
            "page_count": int(status["page_count"]),
            "asset_count": int(status["asset_count"]),
            "fact_count": int(status["fact_count"]),
            "perspective_count": int(status["perspective_count"]),
            "evidence_url_count": int(status["evidence_url_count"]),
        },
    }
    write_json(loop_state_path(plan["batch_id"]), loop_state)

    print(
        "[batch run] OK: "
        f"batch={plan['batch_id']} entities={len(entities)} posts={len(posts)} targets={','.join(selected_targets)}"
    )
    return 0
