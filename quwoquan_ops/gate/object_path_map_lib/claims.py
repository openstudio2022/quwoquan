"""端侧对象归属裁决与云侧 kind 规则防漂移。"""
from __future__ import annotations

import ast
import json
from typing import Sequence

from .constants import APP_SOURCE_SUFFIX, REQUIRED_CLOUD_LAYERS_BY_KIND, ROOT
from .identity import (
    derive_app_cross_cutting_shape_root,
    derive_app_is_composition_root,
    derive_app_layer,
    derive_app_target_shape_identity,
)
from .roster import ObjectRoster


def _filename_alias_candidates(
    file_name: str,
    roster: ObjectRoster,
) -> dict[str, str]:
    """返回文件名前缀 token 串命中的对象别名候选，取最长别名。

    端侧文件名普遍以对象别名开头（`conversation_remote.dart`、
    `post_publication_status_reader.dart`）。只接受 stem 等于别名或以
    ``<alias>_`` 开头，避免子串误命中。
    """
    stem = file_name
    for suffix in (".dart",):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    best_length = 0
    best: dict[str, str] = {}
    for alias, candidates in roster.alias_index.items():
        if stem != alias and not stem.startswith(f"{alias}_"):
            continue
        if len(alias) < best_length:
            continue
        if len(alias) > best_length:
            best_length = len(alias)
            best = {}
        best.update(candidates)
    return best


def _leads_with_token(stem: str, token: str) -> bool:
    """*stem* 的首个 `_` 分词是否恰为 *token*（`content_post_x` 的首段是 `content`）。"""
    return stem == token or stem.startswith(f"{token}_")


def _file_stem(file_name: str) -> str:
    if file_name.endswith(APP_SOURCE_SUFFIX):
        return file_name[: -len(APP_SOURCE_SUFFIX)]
    return file_name


def _filename_domain_qualified_candidates(
    file_name: str,
    roster: ObjectRoster,
) -> dict[str, str]:
    """文件名同时被对象别名与该对象的 domain 限定时的候选，返回 ``{objectId: tier}``。

    这是**目录完全不表达作用域**时唯一被接受的对象级信号，比
    ``filename_object_scoped`` 更严：除了别名命中，还要求文件名首段就是该对象
    的 domain（`content_post_detail_payload.dart` → `content.post`）。

    额外要求 domain 限定不是保守癖好，而是可证伪的必要条件：裁剪出来的短别名
    （`user.user_settings` → `settings`、`circle.circle_file` → `file`、
    `chat.conversation` → `conversation`）在端侧同时是通用 UI 词汇，
    `settings_form.dart`、`file_storage_gateway.dart`、`conversation_sheet.dart`
    都不是对应对象的实现。domain 限定把这类同形词挡在门外，代价是少认几个真归属
    ——派生器宁可欠报也不能错报。
    """
    stem = _file_stem(file_name)
    return {
        object_id: tier
        for object_id, tier in _filename_alias_candidates(file_name, roster).items()
        if _leads_with_token(stem, roster.objects[object_id]["domain"])
    }


def _filename_scope_segment(
    relative_parts: Sequence[str],
    roster: ObjectRoster,
) -> str | None:
    """文件名限定前缀命中的最长 domain / bounded context 名，否则 None。

    与目录作用域回退同性质，只是信号来自文件名：`content_cache_services.dart`
    是 content domain 的实现，不是横切面。它只产出**作用域级**结论
    （`context_only` / `domain_only`），不替业务指定对象。

    附加条件是现状路径必须同时表达 DDD 层角色（``derive_app_layer`` 命中）。
    这一条不是保守癖好：端侧共享设计系统与文案层大量使用 domain 名做**限定词**
    而非归属（`core/constants/chat_text_constants.dart`、
    `core/constants/search_semantic_constants.dart`、
    `core/utils/chat_time_formatter.dart`），它们所在的 `constants` / `utils` /
    `design_system` 目录本来就不表达层。若不要求层，这批横切文件会被反判成 domain，
    进而让 `core/widgets/app_search_field.dart` 这类真横切件凭空产生反向依赖违规
    ——正是本规则要消除的那类假账。
    """
    if derive_app_layer(relative_parts, roster) is None:
        return None
    stem = _file_stem(relative_parts[-1] if relative_parts else "")
    matched = [name for name in roster.scope_names if _leads_with_token(stem, name)]
    return max(matched, key=len) if matched else None


def _scope_claim(segment: str, roster: ObjectRoster) -> dict:
    """把一个作用域段折叠成 ``context_only`` / ``domain_only`` 结论。

    目录段与文件名限定前缀共用本函数，保证「只能反推到作用域」这一结论在两个
    信号来源下完全同义，不出现第二套作用域语义。
    """
    context_ids = roster.contexts_by_name.get(segment)
    if context_ids:
        resolved = sorted(context_ids)
        return {
            "method": "context_only",
            "objectIds": [],
            "contextIds": resolved,
            "ambiguous": len(resolved) > 1,
            "aliasTier": None,
        }
    return {
        "method": "domain_only",
        "objectIds": [],
        "domains": [segment],
        "ambiguous": False,
        "aliasTier": None,
    }


def derive_app_object_claim(
    relative_parts: Sequence[str],
    roster: ObjectRoster,
    page_claims: dict[str, list[str]],
    relative_path: str,
) -> dict:
    """派生一个端侧文件的对象归属。

    信号按权威性排序，第一个成立的胜出：

    1. ``app_target_shape``：文件已处于
       ``service/<service>/<context>/<object>/<layer>/``
       目标形态，身份由物理位置精确决定，与云侧同级。**必须排在最前**：已完成的
       搬迁决定就是最终事实，若让 page contract 或别名启发式覆盖它，已搬迁文件会
       被反推回旧结论（甚至落回 ``multi_object_page`` / ``context_only``），派生失去
       幂等，四条搬迁流会持续收到假归属与假违规。
    2. ``cross_cutting_shape``：文件已处于 ``lib/runtime/**``、
       ``lib/design_system/**`` 或组合根，物理位置即最终横切归属，不能被页面聚合元数据
       反推回某个业务对象。
    3. ``page_object_contract``：``page_object_contract.yaml`` 的
       ``source_path`` 精确命中，``object_ids`` 即归属（可能多于一个）。
    4. ``path_object_scoped``：某目录段命中对象别名，且祖先段已声明该对象的
       domain 或 context（取最右命中段）。
    5. ``path_object_global``：某目录段命中的别名在全 roster 内全局唯一，且该段
       不是作用域名（domain / context 同名段一律按作用域解释）。
    6. ``filename_object_scoped``：目录只能确立作用域，但文件名前缀命中该作用域
       内唯一对象别名。
    7. ``context_only`` / ``domain_only``：只能反推到 bounded context 或 domain；
       作用域既可以来自目录段，也可以来自文件名的 ``<domain>_`` / ``<context>_``
       限定前缀（`core/services/cache/content_cache_services.dart`）。
    8. ``filename_object_qualified``：目录完全不表达作用域，但文件名同时被对象
       别名与该对象的 domain 限定。
    9. ``unowned``：无法反推，归横切面或等待人工裁决。

    任一层级出现多个候选时返回 ``ambiguous``，绝不代替业务任意择一。

    页面映射和别名派生之前必须先让物理位置与组合根语义生效：已经落在 ``lib/runtime/**`` /
    ``lib/design_system/**`` 的文件的结论就是「横切面」（否则
    ``runtime/di/circle_dependencies.dart`` 会被文件名反推成 `circle.circle`，
    破坏派生幂等）；``**/di/**`` 是组合根，按定义横跨 domain、不承载对象身份。
    """
    shape = derive_app_target_shape_identity(relative_parts, roster)
    if shape is not None:
        domain, context, object_name, layer = shape
        return {
            "method": "app_target_shape",
            "objectIds": [roster.by_key[(domain, context, object_name)]["objectId"]],
            "ambiguous": False,
            "aliasTier": None,
            "targetLayer": layer,
        }

    if (
        derive_app_cross_cutting_shape_root(relative_parts) is not None
        or derive_app_is_composition_root(relative_parts)
    ):
        return {
            "method": "unowned",
            "objectIds": [],
            "ambiguous": False,
            "aliasTier": None,
        }

    if relative_path in page_claims:
        object_ids = sorted(page_claims[relative_path])
        return {
            "method": "page_object_contract",
            "objectIds": object_ids,
            "ambiguous": len(object_ids) > 1,
            "aliasTier": None,
        }

    directories = list(relative_parts[:-1])
    file_name = relative_parts[-1] if relative_parts else ""
    for index in range(len(directories) - 1, -1, -1):
        segment = directories[index]
        candidates = roster.alias_index.get(segment)
        if not candidates:
            continue
        ancestors = directories[:index]
        scoped = sorted(
            object_id
            for object_id in candidates
            if roster.scope_matches(object_id, ancestors)
        )
        if len(scoped) == 1:
            return {
                "method": "path_object_scoped",
                "objectIds": scoped,
                "ambiguous": False,
                "aliasTier": candidates[scoped[0]],
            }
        if scoped:
            return {
                "method": "path_object_scoped",
                "objectIds": scoped,
                "ambiguous": True,
                "aliasTier": None,
            }
        if segment in roster.scope_names:
            # 与 domain / context 同名的段按作用域解释，交给下面的作用域回退。
            break
        if len(candidates) == 1:
            object_id = next(iter(candidates))
            return {
                "method": "path_object_global",
                "objectIds": [object_id],
                "ambiguous": False,
                "aliasTier": candidates[object_id],
            }
        return {
            "method": "path_object_global",
            "objectIds": sorted(candidates),
            "ambiguous": True,
            "aliasTier": None,
        }

    scope_index = None
    for index in range(len(directories) - 1, -1, -1):
        if directories[index] in roster.scope_names:
            scope_index = index
            break

    if scope_index is None and not (
        derive_app_cross_cutting_shape_root(relative_parts) is not None
        or derive_app_is_composition_root(relative_parts)
    ):
        # 目录不表达作用域时，文件名的限定前缀是唯一剩余的受控信号。
        qualified = _filename_domain_qualified_candidates(file_name, roster)
        if qualified:
            return {
                "method": "filename_object_qualified",
                "objectIds": sorted(qualified),
                "ambiguous": len(qualified) > 1,
                "aliasTier": (
                    qualified[next(iter(qualified))] if len(qualified) == 1 else None
                ),
            }
        scope_from_file_name = _filename_scope_segment(relative_parts, roster)
        if scope_from_file_name is not None:
            return _scope_claim(scope_from_file_name, roster)

    if scope_index is not None:
        segment = directories[scope_index]
        filename_candidates = {
            object_id: tier
            for object_id, tier in _filename_alias_candidates(file_name, roster).items()
            if segment
            in {roster.objects[object_id]["domain"], roster.objects[object_id]["context"]}
        }
        if len(filename_candidates) == 1:
            object_id = next(iter(filename_candidates))
            return {
                "method": "filename_object_scoped",
                "objectIds": [object_id],
                "ambiguous": False,
                "aliasTier": filename_candidates[object_id],
            }
        if filename_candidates:
            return {
                "method": "filename_object_scoped",
                "objectIds": sorted(filename_candidates),
                "ambiguous": True,
                "aliasTier": None,
            }
        return _scope_claim(segment, roster)

    return {
        "method": "unowned",
        "objectIds": [],
        "ambiguous": False,
        "aliasTier": None,
    }


# ---------------------------------------------------------------------------
# 云侧 kind 规则防漂移
# ---------------------------------------------------------------------------


def check_cloud_layer_rule_mirror() -> list[str]:
    """AST 比对本包的云侧 kind 规则与 verify_service_architecture.py 的原表。"""
    gate_path = ROOT / "quwoquan_ops" / "gate" / "verify_service_architecture.py"
    try:
        tree = ast.parse(gate_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [f"{gate_path.name}: 云侧 kind 规则不可读，无法证明同源: {exc}"]
    literal: dict | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "verify_kind_aware_object_implementation":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            targets = [t.id for t in statement.targets if isinstance(t, ast.Name)]
            if "required_layers" not in targets:
                continue
            try:
                literal = ast.literal_eval(statement.value)
            except ValueError:
                return ["verify_service_architecture.py: required_layers 不是字面量"]
    if literal is None:
        return [
            "verify_service_architecture.py: 未找到 "
            "verify_kind_aware_object_implementation.required_layers"
        ]
    upstream = {kind: tuple(sorted(layers)) for kind, layers in literal.items()}
    mirrored = {
        kind: tuple(sorted(layers))
        for kind, layers in REQUIRED_CLOUD_LAYERS_BY_KIND.items()
    }
    if upstream != mirrored:
        return [
            "REQUIRED_CLOUD_LAYERS_BY_KIND 与 verify_service_architecture.py 漂移: "
            f"upstream={json.dumps(upstream, sort_keys=True)} "
            f"mirrored={json.dumps(mirrored, sort_keys=True)}"
        ]
    return []
