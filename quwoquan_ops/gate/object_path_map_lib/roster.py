"""ContractGraph 对象 roster 与别名派生。"""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .constants import ALIAS_TRIM_SUFFIXES


class ObjectRoster:
    """ContractGraph 派生的对象 roster，是本工具唯一的对象身份来源。"""

    def __init__(self, graph: dict) -> None:
        self.objects: dict[str, dict] = {}
        self.context_ids: set[str] = set()
        for entry in graph.get("objects") or []:
            object_id = str(entry.get("id") or "")
            source_path = str(entry.get("sourcePath") or "")
            parts = source_path.split("/")
            if not object_id or len(parts) < 3:
                continue
            domain = str(entry.get("domain") or parts[0])
            context = parts[1]
            object_name = parts[2]
            self.objects[object_id] = {
                "objectId": object_id,
                "domain": domain,
                "context": context,
                "contextId": f"{domain}.{context}",
                "objectName": object_name,
                "name": str(entry.get("name") or ""),
                "kind": str(entry.get("kind") or ""),
                "contractSourcePath": source_path,
            }
        for entry in graph.get("businessObjectMaps") or []:
            for context in entry.get("boundedContexts") or []:
                context_id = str(context.get("contextId") or "")
                if context_id:
                    self.context_ids.add(context_id)

        self.by_key: dict[tuple[str, str, str], dict] = {
            (record["domain"], record["context"], record["objectName"]): record
            for record in self.objects.values()
        }
        app_operations: dict[str, list[str]] = defaultdict(list)
        for operation in graph.get("operations") or []:
            object_id = str(operation.get("objectId") or "")
            operation_id = str(operation.get("id") or "")
            client_contract = operation.get("clientContract")
            if (
                object_id not in self.objects
                or not operation_id
                or not isinstance(client_contract, dict)
                or not client_contract
            ):
                continue
            app_operations[object_id].append(operation_id)
        self.app_client_contract_operations: dict[str, tuple[str, ...]] = {
            object_id: tuple(sorted(operation_ids))
            for object_id, operation_ids in sorted(app_operations.items())
        }
        self.domains: set[str] = {record["domain"] for record in self.objects.values()}
        self.contexts_by_name: dict[str, set[str]] = defaultdict(set)
        for record in self.objects.values():
            self.contexts_by_name[record["context"]].add(record["contextId"])

        #: domain 名与 context 名构成「作用域段」集合。作用域段与对象别名可能同名
        #: （如 `circle` 既是 domain 又是 `circle.circle`）；此时该段优先按作用域
        #: 解释，只有在祖先段已确立作用域后才允许按对象解释，避免把 domain
        #: 作用域段误判成同名对象。
        self.scope_names: set[str] = self.domains | set(self.contexts_by_name)

        # alias → {objectId: tier}
        self.alias_index: dict[str, dict[str, str]] = defaultdict(dict)
        for record in self.objects.values():
            for alias, tier in object_aliases(record["domain"], record["objectName"]):
                previous = self.alias_index[alias].get(record["objectId"])
                if previous is None or _tier_rank(tier) < _tier_rank(previous):
                    self.alias_index[alias][record["objectId"]] = tier

    def record(self, object_id: str) -> dict | None:
        return self.objects.get(object_id)

    def scope_matches(self, object_id: str, segments: Sequence[str]) -> bool:
        """路径祖先段是否声明了该对象的 domain 或 context。"""
        record = self.objects[object_id]
        return record["domain"] in segments or record["context"] in segments


def _tier_rank(tier: str) -> int:
    #: `domain_prefixed` 是叠加在其它别名之上的再变换，因此排在最弱：`circle_behavior`
    #: 既能由 canonical 裁后缀得到，也能由 `behavior` 加前缀得到，报告前者。
    order = ("canonical", "domain_trimmed", "suffix_trimmed", "domain_prefixed")
    return order.index(tier) if tier in order else len(order)


def object_aliases(domain: str, object_name: str) -> list[tuple[str, str]]:
    """派生对象的目录/文件名别名集合，返回 ``(alias, tier)``。

    端侧现状命名只在三种情况下偏离 canonical 对象名，且三者都由 roster 自身
    的 ``(domain, objectName)`` 机械派生，不接受任何人工同义词表，避免引入
    第二真相源：

    - ``domain_trimmed``：省略 domain 前缀
      （`circle.circle_behavior_fact` → `behavior_fact`）。
    - ``suffix_trimmed``：省略语义后缀
      （`content.outbound_share_fact` → `outbound_share`）。
    - ``domain_prefixed``：反过来用 domain 限定对象名
      （`content.post` → `content_post`，见 `content_post_view_data.dart`）。
      它是 ``domain_trimmed`` 的逆向同构，端侧现状文件名普遍靠这个前缀把
      `post` / `report` 这类通用词限定回具体 domain。
    """
    aliases: list[tuple[str, str]] = [(object_name, "canonical")]
    if object_name.startswith(f"{domain}_") and len(object_name) > len(domain) + 1:
        aliases.append((object_name[len(domain) + 1 :], "domain_trimmed"))
    for alias, tier in list(aliases):
        for suffix in ALIAS_TRIM_SUFFIXES:
            if alias.endswith(suffix) and len(alias) > len(suffix):
                aliases.append((alias[: -len(suffix)], "suffix_trimmed"))
    for alias, tier in list(aliases):
        if alias != domain and not alias.startswith(f"{domain}_"):
            aliases.append((f"{domain}_{alias}", "domain_prefixed"))
    seen: dict[str, str] = {}
    for alias, tier in aliases:
        if alias and (alias not in seen or _tier_rank(tier) < _tier_rank(seen[alias])):
            seen[alias] = tier
    return sorted(seen.items())
