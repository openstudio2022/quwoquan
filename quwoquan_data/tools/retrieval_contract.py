from __future__ import annotations

from typing import Any


LOCATION_SEARCH_NAME_MAP = {
    "杭州": "Hangzhou",
    "北京": "Beijing",
    "上海": "Shanghai",
    "深圳": "Shenzhen",
    "广州": "Guangzhou",
}


def default_location_search_name(location: str) -> str:
    return LOCATION_SEARCH_NAME_MAP.get(location.strip(), location.strip())


RETRIEVAL_PROMPT_CONTRACT = """你是 quwoquan_data 的命令式证据采集规划器。

请严格输出一个 JSON 对象，不要输出 JSON 之外的文字。字段如下：
- query: 主检索短词，直接面向本轮最重要的补齐目标
- search_queries: 数组；每项都包含 dimension、query、purpose、entity_refs、tag_refs、target_domains
- location: 当前批次的地点中文名；如没有则输出空字符串
- location_search_name: 适合公开网页检索的地理名英文/拉丁写法；如没有则输出空字符串
- target_domains: 本轮优先保留证据的域名列表
- round: 本轮轮次
- status: planned 或 ready_for_finalize 或 exhausted

约束：
1. query 必须短而明确，不要把整段自然语言塞进去。
2. search_queries 要优先补齐缺失实体、缺失标签和缺失内容视角，而不是机械重复主 query。
3. 每条 search_queries 都要写清 purpose，解释为什么这一条能补齐当前缺口。
4. 只能规划公开可核验的网页证据；不要假设登录态、验证码绕过或受限接口。
5. 输出中必须保留 entity_refs 和 tag_refs，便于后续把证据落到 raw/ 与 facts.ndjson。
"""


def build_retrieval_prompt_context(
    *,
    batch_id: str,
    main_query: str,
    next_round: int,
    location: str,
    location_search_name: str,
    target_domains: list[str],
    missing_entity_refs: list[str],
    missing_tag_refs: list[str],
    fact_count: int,
) -> str:
    return (
        f"batch_id={batch_id}\n"
        f"main_query={main_query}\n"
        f"next_round={next_round}\n"
        f"location={location}\n"
        f"location_search_name={location_search_name}\n"
        f"target_domains={', '.join(target_domains)}\n"
        f"missing_entity_refs={missing_entity_refs}\n"
        f"missing_tag_refs={missing_tag_refs}\n"
        f"fact_count={fact_count}\n"
    )


def build_retrieval_prompt(
    *,
    batch_id: str,
    main_query: str,
    next_round: int,
    location: str,
    location_search_name: str,
    target_domains: list[str],
    missing_entity_refs: list[str],
    missing_tag_refs: list[str],
    fact_count: int,
) -> str:
    context = build_retrieval_prompt_context(
        batch_id=batch_id,
        main_query=main_query,
        next_round=next_round,
        location=location,
        location_search_name=location_search_name,
        target_domains=target_domains,
        missing_entity_refs=missing_entity_refs,
        missing_tag_refs=missing_tag_refs,
        fact_count=fact_count,
    )
    return f"{RETRIEVAL_PROMPT_CONTRACT}\n\n当前批次上下文：\n{context}"


def search_query_item(
    *,
    dimension: str,
    query: str,
    purpose: str,
    round_number: int,
    target_domains: list[str],
    entity_refs: list[str] | None = None,
    tag_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "query": query,
        "purpose": purpose,
        "round": round_number,
        "status": "pending",
        "target_domains": target_domains,
        "entity_refs": entity_refs or [],
        "tag_refs": tag_refs or [],
    }
