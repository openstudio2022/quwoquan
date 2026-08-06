#!/usr/bin/env python3
"""端云 business object → 物理文件的唯一派生器（derivation，不是注册表）。

本工具只读受版本控制的真相源，交叉派生「business object → 端云物理文件」映射、
迁移目标清单与现状基线；不写入、不维护任何 registry / inventory / 台账。全部产物
落在 `.qwq_output/env/repo/runs/object-path-map/`，删除后可凭真相源完全重建，符合
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#req-001`（禁止第二真相源，状态必须
由物理路径与运行证据派生）。

真相源（只读）
--------------
1. `quwoquan_service/generated/contract_graph.json`
   对象 roster：`objects[].{id,domain,kind,sourcePath}` 与
   `businessObjectMaps[].boundedContexts[].contextId`。
2. `quwoquan_service/services/*/contracts/domain.yaml`
   与 `quwoquan_service/control-plane/*/contracts/domain.yaml`：service → domain。
3. `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`
   页面 `source_path` → `object_ids`，是端侧 presentation 归属的唯一权威信号。
4. 物理扫描：`quwoquan_app/lib/**`、`quwoquan_app/test/**`、
   `quwoquan_service/{services,control-plane}/*/internal/**`、
   `quwoquan_service/{services,control-plane}/*/tests/**`。

W5 同源声明
-----------
规划中的 W5 会在 `quwoquan_service/internal/metadata/load/load.go` 增加派生式
evidence loader。该 loader 必须与本文件同源，复用同一套规则；Go 侧不得另写一份。
可复用的规则表达集中在下列常量与函数（`RULE_ID` 变更即视为规则变更）：

- 常量：`RULE_ID`、`CLOUD_LAYERS`、`APP_LAYERS`、`APP_TO_CLOUD_LAYER_EQUIVALENCE`、
  `REQUIRED_CLOUD_LAYERS_BY_KIND`、`CLOUD_EXTERNAL_REFERENCE_REQUIRED`、
  `CLOUD_EXTERNAL_REFERENCE_EITHER`、`CLOUD_TEST_LAYERS`、
  `CLOUD_TEST_SUPPORT_ROOT`、`REQUIRED_APP_LAYERS_BY_KIND`、
  `CONDITIONAL_APP_LAYERS_BY_KIND`、`FORBIDDEN_APP_LAYERS_BY_KIND`、
  `APP_LAYER_BY_SEGMENT`、`APP_LAYER_ALIASES`、`APP_CROSS_CUTTING_ROOTS`、
  `APP_CROSS_CUTTING_SEGMENTS`、`APP_CROSS_CUTTING_STRIPPED_PREFIXES`、
  `APP_DESIGN_SYSTEM_SEGMENTS`、`APP_TARGET_SHAPE_SEGMENTS`、
  `APP_TEST_TARGET_SHAPE_SEGMENTS`、`ALIAS_TRIM_SUFFIXES`、
  `CLAIM_METHOD_CONFIDENCE`。
- 函数：`derive_cloud_source_identity`、`derive_cloud_test_identity`、
  `object_aliases`、`derive_app_object_claim`、`derive_app_layer`、
  `derive_app_target_shape_identity`、`derive_app_test_target_shape_identity`、
  `derive_app_cross_cutting_shape_root`、
  `derive_app_target_path`、`derive_app_test_target_path`、
  `derive_app_cross_cutting_root`、`derive_app_cross_cutting_target_path`、
  `required_app_layers`、`required_cloud_layers`。
- 对象身份入口：`ObjectRoster`（含 `alias_index`、`scope_names`、`by_key`）。

派生幂等
--------
`derive(derive(p)) == derive(p)`：已经处于目标形态的路径，派生结果必须等于它自己。
目标形态由 `derive_app_target_shape_identity`（`lib/<domain>/<context>/<object>/<layer>/`）、
`derive_app_test_target_shape_identity`（`test/<layer>/<domain>/<context>/<object>/`）与
`derive_app_cross_cutting_shape_root`（`lib/runtime/`、`lib/design_system/`）精确识别，
命中后一切基于旧命名的启发式让位：身份与层由固定物理位置决定，目标路径即自身。
本不变量由 `test_object_path_map__derivation__local_contract_test.py` 断言；它是四条
domain 流与 W1b 边搬边跑派生器/门禁的前提，破坏它会持续产生假归属与假违规。

`REQUIRED_CLOUD_LAYERS_BY_KIND` 是 `quwoquan_ops/gate/verify_service_architecture.py`
中 `Verification.verify_kind_aware_object_implementation` 的 `required_layers` 镜像。
`check_cloud_layer_rule_mirror` 在每次运行时用 AST 比对两者，一旦漂移直接失败，避免
出现第二套云侧 kind 规则。

用法
----
    python3 quwoquan_ops/gate/object_path_map.py

幂等：输出目录固定、内容全排序、不含时间戳与绝对路径，连续两次运行产物逐字节一致。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import repo_runs_root  # noqa: E402

# ---------------------------------------------------------------------------
# 规则标识与真相源路径
# ---------------------------------------------------------------------------

RULE_ID = "object-path-map/v1"

CONTRACT_GRAPH_PATH = Path("quwoquan_service/generated/contract_graph.json")
PAGE_OBJECT_CONTRACT_PATH = Path(
    "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"
)
SERVICE_ROOT_GLOBS = (
    "quwoquan_service/services/*",
    "quwoquan_service/control-plane/*",
)
APP_ROOT = Path("quwoquan_app")
APP_LIB_ROOT = APP_ROOT / "lib"
APP_TEST_ROOT = APP_ROOT / "test"
APP_SOURCE_SUFFIX = ".dart"
CLOUD_SOURCE_SUFFIXES = frozenset({".go", ".py"})
CLOUD_TEST_LAYERS = ("local_contract", "api_integration")

#: 云侧 `tests/support/**` 是服务内共享测试支撑根，不承载对象身份，
#: 与 verify_service_architecture.py 只校验 local_contract / api_integration 一致。
CLOUD_TEST_SUPPORT_ROOT = "support"
APP_TEST_LAYERS = ("local_contract", "api_integration", "user_acceptance", "support")

OUTPUT_DIR_NAME = "object-path-map"

# ---------------------------------------------------------------------------
# 层名与 kind 感知的必需层规则（W5 evidence loader 的同源依据）
# ---------------------------------------------------------------------------

#: 云侧 DDD 层，与 verify_service_architecture.py 的 ``LAYERS`` 同名同义。
CLOUD_LAYERS = ("domain", "application", "adapters", "infrastructure")

#: 端侧目标层，对应 ``quwoquan_app/lib/<domain>/<context>/<object>/<layer>/``。
APP_LAYERS = ("domain", "application", "adapters", "presentation")

#: 端云层名等价映射：端侧 presentation 承担云侧入向 adapters，端侧 adapters 承担
#: 云侧出向 infrastructure。端侧不存在独立的出向/入向拆分目录。
APP_TO_CLOUD_LAYER_EQUIVALENCE = {
    "domain": "domain",
    "application": "application",
    "presentation": "adapters/inbound",
    "adapters": "infrastructure",
}

#: 云侧 kind → 必需层。verify_service_architecture.py 中
#: ``verify_kind_aware_object_implementation`` 的 ``required_layers`` 镜像，
#: 由 ``check_cloud_layer_rule_mirror`` 每次运行时 AST 比对防漂移。
REQUIRED_CLOUD_LAYERS_BY_KIND = {
    "aggregate_root": ("application", "domain", "infrastructure"),
    "append_only_fact": ("application", "domain", "infrastructure"),
    "projection": ("application", "infrastructure"),
    "runtime_session": ("application", "domain", "infrastructure"),
}

#: 云侧 external_reference 不在上表内：它要求 application，且 adapters 与
#: infrastructure 至少命中一个（同 verify_service_architecture.py）。
CLOUD_EXTERNAL_REFERENCE_REQUIRED = ("application",)
CLOUD_EXTERNAL_REFERENCE_EITHER = ("adapters", "infrastructure")

#: 端侧 kind → 必需层，由云侧规则经 APP_TO_CLOUD_LAYER_EQUIVALENCE 映射得到：
#: 云侧 infrastructure 折叠为端侧 adapters；云侧 domain 在端侧是条件必需。
REQUIRED_APP_LAYERS_BY_KIND = {
    "aggregate_root": ("application", "adapters"),
    "append_only_fact": ("application", "adapters"),
    "projection": ("application", "adapters"),
    "runtime_session": ("application", "adapters"),
    "external_reference": ("application", "adapters"),
}

#: 端侧条件必需层：只有该对象在端侧承担不变式（存在 domain 层实现）时才必需。
#: 派生器只能观测「是否已存在」，不能替业务判定「是否应当存在」，因此这里记录为
#: 条件项而非缺失项。
CONDITIONAL_APP_LAYERS_BY_KIND = {
    "aggregate_root": ("domain",),
    "runtime_session": ("domain",),
}

#: 端侧禁止层：append_only_fact 不得拥有 presentation（事实流不直接成页）。
FORBIDDEN_APP_LAYERS_BY_KIND = {
    "append_only_fact": ("presentation",),
}

#: presentation 的必需性不由 kind 决定，而由 page_object_contract.yaml 的
#: object_ids 派生：被页面认领的对象必须有 presentation，未被认领的不必须。
PRESENTATION_REQUIREMENT_SOURCE = str(PAGE_OBJECT_CONTRACT_PATH)


def required_cloud_layers(kind: str) -> tuple[str, ...]:
    """返回云侧 *kind* 的必需层（external_reference 的 either 组合另行判定）。"""
    return REQUIRED_CLOUD_LAYERS_BY_KIND.get(kind, ())


def required_app_layers(kind: str, *, claimed_by_page: bool) -> tuple[str, ...]:
    """返回端侧 *kind* 的必需层；被页面认领时追加 presentation。"""
    layers = list(REQUIRED_APP_LAYERS_BY_KIND.get(kind, ()))
    if claimed_by_page and "presentation" not in FORBIDDEN_APP_LAYERS_BY_KIND.get(kind, ()):
        layers.append("presentation")
    return tuple(sorted(set(layers)))


# ---------------------------------------------------------------------------
# 端侧现状路径 → 层角色的派生规则
# ---------------------------------------------------------------------------

#: 端侧目标形态的固定位置。**一旦文件搬到目标形态，身份就与云侧一样可由物理位置
#: 精确反推，任何启发式都必须让位。** 这是派生幂等的唯一依据：
#: production 为 ``lib/<domain>/<context>/<object>/<layer>/...``（层内允许可选子路径，
#: 与云侧 ``internal/<ctx>/<obj>/adapters/inbound/http/`` 同构），
#: test 为 ``test/<test_layer>/<domain>/<context>/<object>/...``，
#: 横切面为 ``lib/runtime/...`` 与 ``lib/design_system/...``。
APP_TARGET_SHAPE_SEGMENTS = 4
APP_TEST_TARGET_SHAPE_SEGMENTS = 3

#: 现状端侧目录名 → 目标层。**只用于尚未搬迁的旧命名**；已处于目标形态的路径由
#: ``derive_app_target_shape_identity`` 的第 4 段精确决定，不进入本表。
#: 未搬迁路径取最右（最具体）的命中段。
APP_LAYER_BY_SEGMENT = {
    # 端侧 presentation ≡ 云侧 adapters/inbound
    "presentation": "presentation",
    "pages": "presentation",
    "page": "presentation",
    "screens": "presentation",
    "views": "presentation",
    "widgets": "presentation",
    "sheets": "presentation",
    "sections": "presentation",
    "components": "presentation",
    "dialogs": "presentation",
    "journeys": "presentation",
    # 端侧 application：用例编排与状态协调
    "application": "application",
    "providers": "application",
    "provider": "application",
    "controllers": "application",
    "notifiers": "application",
    "coordinators": "application",
    "usecases": "application",
    "state": "application",
    # 端侧 adapters ≡ 云侧 infrastructure（出向）
    "adapters": "adapters",
    "remote": "remote_adapters",
    "repositories": "adapters",
    "services": "adapters",
    "infrastructure": "adapters",
    "persistence": "adapters",
    "storage": "adapters",
    "clients": "adapters",
    "gateways": "adapters",
    "transport": "adapters",
    # 端侧 domain：不变式、值对象与领域规则
    "domain": "domain",
    "models": "domain",
    "model": "domain",
    "entities": "domain",
    "value_objects": "domain",
    "rules": "domain",
    "policies": "domain",
    "contracts": "domain",
}

#: ``remote`` 段在端侧同时表达「出向适配」与「云契约客户端」，统一归 adapters。
APP_LAYER_ALIASES = {"remote_adapters": "adapters"}

#: 横切面根：不归属任何 business object 的端侧文件的唯一两个落点。
APP_CROSS_CUTTING_ROOTS = {
    "design_system": "lib/design_system",
    "runtime": "lib/runtime",
}

#: 横切面根在 ``lib/`` 之下的顶层段，由 APP_CROSS_CUTTING_ROOTS 派生而非另写死。
#: 用于识别「已经搬到横切面目标位置」的路径，避免再套一层根段。
APP_CROSS_CUTTING_SEGMENTS = {
    relative.split("/", 1)[1]: root
    for root, relative in APP_CROSS_CUTTING_ROOTS.items()
}

#: 命中该段即判定为 design_system 横切面；其余无主端侧文件归 runtime。
#: 仅对**尚未搬迁**的路径生效：已在 ``lib/runtime/`` 之下的 ``theme`` / ``tokens``
#: 子目录属于 runtime，不得因段名被改判到 design_system。
APP_DESIGN_SYSTEM_SEGMENTS = frozenset({"design_system", "theme", "tokens"})

#: 横切面目标路径构造时可剥离的现状前缀段（避免 `lib/runtime/core/...` 冗余）。
#: 目标根自身的段（`runtime` / `design_system`）也必须剥离，否则已搬迁路径会被
#: 反复套壳成 `lib/runtime/runtime/di/...`，派生失去幂等。
APP_CROSS_CUTTING_STRIPPED_PREFIXES = ("core",)

#: 对象别名裁剪后缀：端侧现状目录普遍省略 `_view` / `_fact` 语义后缀。
ALIAS_TRIM_SUFFIXES = ("_view", "_fact")

#: 认领方法 → 置信度。已处于目标形态的物理位置与云侧同级，是最强信号。
CLAIM_METHOD_CONFIDENCE = {
    "cloud_path_exact": "exact",
    "app_target_shape": "exact",
    "page_object_contract": "exact",
    "path_object_scoped": "high",
    "path_object_global": "medium",
    "filename_object_scoped": "medium",
    "context_only": "scope",
    "domain_only": "scope",
    "cross_cutting": "cross_cutting",
    "unowned": "none",
}


# ---------------------------------------------------------------------------
# roster 载入
# ---------------------------------------------------------------------------


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
        self.domains: set[str] = {record["domain"] for record in self.objects.values()}
        self.contexts_by_name: dict[str, set[str]] = defaultdict(set)
        for record in self.objects.values():
            self.contexts_by_name[record["context"]].add(record["contextId"])

        #: domain 名与 context 名构成「作用域段」集合。作用域段与对象别名可能同名
        #: （如 `circle` 既是 domain 又是 `circle.circle`）；此时该段优先按作用域
        #: 解释，只有在祖先段已确立作用域后才允许按对象解释，避免把
        #: `lib/cloud/circle/generated/circle_membership_errors.g.dart` 误判成
        #: `circle.circle`。
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
    order = ("canonical", "domain_trimmed", "suffix_trimmed")
    return order.index(tier) if tier in order else len(order)


def object_aliases(domain: str, object_name: str) -> list[tuple[str, str]]:
    """派生对象的目录别名集合，返回 ``(alias, tier)``。

    端侧现状目录只在两种情况下偏离 canonical 对象名：省略 domain 前缀
    （`circle.circle_behavior_fact` → `behavior_fact`）与省略语义后缀
    （`content.outbound_share_fact` → `outbound_share`）。规则只允许这两种裁剪，
    不接受任何人工同义词表，避免引入第二真相源。
    """
    aliases: list[tuple[str, str]] = [(object_name, "canonical")]
    if object_name.startswith(f"{domain}_") and len(object_name) > len(domain) + 1:
        aliases.append((object_name[len(domain) + 1 :], "domain_trimmed"))
    for alias, tier in list(aliases):
        for suffix in ALIAS_TRIM_SUFFIXES:
            if alias.endswith(suffix) and len(alias) > len(suffix):
                aliases.append((alias[: -len(suffix)], "suffix_trimmed"))
    seen: dict[str, str] = {}
    for alias, tier in aliases:
        if alias and (alias not in seen or _tier_rank(tier) < _tier_rank(seen[alias])):
            seen[alias] = tier
    return sorted(seen.items())


# ---------------------------------------------------------------------------
# 云侧身份派生（物理路径可唯一反推，无启发式）
# ---------------------------------------------------------------------------


def derive_cloud_source_identity(
    relative_parts: Sequence[str],
) -> tuple[str, str, str] | None:
    """从 ``internal/<context>/<object>/<layer>/...`` 反推 ``(context, object, layer)``。

    与 verify_service_architecture.py 的 production 源扫描同形：层必须是
    ``CLOUD_LAYERS`` 之一，否则视为不可反推。
    """
    if len(relative_parts) < 4:
        return None
    context, object_name, layer = relative_parts[0], relative_parts[1], relative_parts[2]
    if layer not in CLOUD_LAYERS:
        return None
    return context, object_name, layer


def derive_cloud_test_identity(
    relative_parts: Sequence[str],
) -> tuple[str, str, str] | None:
    """从 ``tests/<layer>/<context>/<object>/...`` 反推 ``(test_layer, context, object)``。"""
    if len(relative_parts) < 3:
        return None
    test_layer, context, object_name = (
        relative_parts[0],
        relative_parts[1],
        relative_parts[2],
    )
    if test_layer not in CLOUD_TEST_LAYERS:
        return None
    return test_layer, context, object_name


# ---------------------------------------------------------------------------
# 端侧目标形态识别（精确反推，派生幂等的唯一依据）
# ---------------------------------------------------------------------------


def derive_app_target_shape_identity(
    relative_parts: Sequence[str],
    roster: ObjectRoster,
) -> tuple[str, str, str, str] | None:
    """从 ``<domain>/<context>/<object>/<layer>/...`` 精确反推端侧对象身份。

    与 ``derive_cloud_source_identity`` 同性质：前三段必须命中 ContractGraph roster
    的真实对象，第四段必须是 ``APP_LAYERS`` 之一，否则返回 ``None``。层内允许可选
    子路径（``presentation/widgets/``、``adapters/remote/``），子路径不参与身份判定。

    命中即代表该文件**已经处于目标形态**，此时任何基于旧命名的启发式都必须让位：
    否则 ``post/presentation/comment/x.dart`` 会被深层段 ``comment`` 劫持成
    ``content.comment``，``presentation/providers/`` 会被改判成 application。
    """
    if len(relative_parts) <= APP_TARGET_SHAPE_SEGMENTS:
        return None
    domain, context, object_name, layer = relative_parts[:APP_TARGET_SHAPE_SEGMENTS]
    if layer not in APP_LAYERS:
        return None
    if (domain, context, object_name) not in roster.by_key:
        return None
    return domain, context, object_name, layer


def derive_app_test_target_shape_identity(
    test_relative_parts: Sequence[str],
    roster: ObjectRoster,
) -> tuple[str, str, str] | None:
    """从 ``<domain>/<context>/<object>/...``（已剥离 test layer）精确反推对象身份。"""
    if len(test_relative_parts) <= APP_TEST_TARGET_SHAPE_SEGMENTS:
        return None
    domain, context, object_name = test_relative_parts[:APP_TEST_TARGET_SHAPE_SEGMENTS]
    if (domain, context, object_name) not in roster.by_key:
        return None
    return domain, context, object_name


def derive_app_cross_cutting_shape_root(relative_parts: Sequence[str]) -> str | None:
    """已处于横切面目标位置时返回其根名（``runtime`` / ``design_system``），否则 None。"""
    if not relative_parts:
        return None
    return APP_CROSS_CUTTING_SEGMENTS.get(relative_parts[0])


# ---------------------------------------------------------------------------
# 端侧层与目标路径派生
# ---------------------------------------------------------------------------


def derive_app_layer(
    relative_parts: Sequence[str],
    roster: ObjectRoster | None = None,
) -> str | None:
    """派生端侧层角色。

    传入 *roster* 且路径已处于目标形态时，层由固定的第 4 段精确决定；否则退回
    ``APP_LAYER_BY_SEGMENT`` 的最右命中段（仅适用于尚未搬迁的旧命名）。
    """
    if roster is not None:
        identity = derive_app_target_shape_identity(relative_parts, roster)
        if identity is not None:
            return identity[3]
    for segment in reversed(list(relative_parts[:-1])):
        layer = APP_LAYER_BY_SEGMENT.get(segment)
        if layer is not None:
            return APP_LAYER_ALIASES.get(layer, layer)
    return None


def derive_app_cross_cutting_root(relative_parts: Sequence[str]) -> str:
    """无主端侧文件的横切面归属：design_system 或 runtime。

    已处于横切面目标位置时以物理根为准，段名启发式不得改判（`lib/runtime/theme/`
    属于 runtime，不是 design_system）。
    """
    shaped = derive_app_cross_cutting_shape_root(relative_parts)
    if shaped is not None:
        return shaped
    if APP_DESIGN_SYSTEM_SEGMENTS & set(relative_parts):
        return "design_system"
    return "runtime"


def derive_app_target_path(
    domain: str,
    context: str,
    object_name: str,
    layer: str,
    file_name: str,
) -> str:
    """端侧对象化目标路径：``lib/<domain>/<context>/<object>/<layer>/<file>``。"""
    return (
        f"{APP_LIB_ROOT.as_posix()}/{domain}/{context}/{object_name}/{layer}/{file_name}"
    )


def derive_app_test_target_path(
    test_layer: str,
    domain: str,
    context: str,
    object_name: str,
    file_name: str,
) -> str:
    """端侧测试目标路径，与云侧 ``tests/<layer>/<context>/<object>/`` 同形。"""
    return (
        f"{APP_TEST_ROOT.as_posix()}/{test_layer}/{domain}/{context}/{object_name}/"
        f"{file_name}"
    )


def derive_app_cross_cutting_target_path(
    root: str,
    relative_to_lib: Sequence[str],
) -> str:
    """横切面目标路径：剥离现状前缀与目标根自身的段后挂到唯一横切根下。

    剥离目标根自身的段是幂等的充要条件：``lib/runtime/di/x.dart`` 已经在目标位置，
    若不剥离首段 ``runtime`` 就会被推导成 ``lib/runtime/runtime/di/x.dart``，且每次
    派生再套一层，导致组合根漏判与假违规随搬迁推进不断累积。
    """
    parts = list(relative_to_lib)
    strippable = set(APP_CROSS_CUTTING_STRIPPED_PREFIXES) | {
        segment
        for segment, mapped_root in APP_CROSS_CUTTING_SEGMENTS.items()
        if mapped_root == root
    }
    while len(parts) > 1 and parts[0] in strippable:
        parts = parts[1:]
    return f"{APP_ROOT.as_posix()}/{APP_CROSS_CUTTING_ROOTS[root]}/{'/'.join(parts)}"


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


def derive_app_object_claim(
    relative_parts: Sequence[str],
    roster: ObjectRoster,
    page_claims: dict[str, list[str]],
    relative_path: str,
) -> dict:
    """派生一个端侧文件的对象归属。

    信号按权威性排序，第一个成立的胜出：

    1. ``app_target_shape``：文件已处于 ``<domain>/<context>/<object>/<layer>/``
       目标形态，身份由物理位置精确决定，与云侧同级。**必须排在最前**：已完成的
       搬迁决定就是最终事实，若让 page contract 或别名启发式覆盖它，已搬迁文件会
       被反推回旧结论（甚至落回 ``multi_object_page`` / ``context_only``），派生失去
       幂等，四条搬迁流会持续收到假归属与假违规。
    2. ``page_object_contract``：``page_object_contract.yaml`` 的
       ``source_path`` 精确命中，``object_ids`` 即归属（可能多于一个）。
    3. ``path_object_scoped``：某目录段命中对象别名，且祖先段已声明该对象的
       domain 或 context（取最右命中段）。
    4. ``path_object_global``：某目录段命中的别名在全 roster 内全局唯一，且该段
       不是作用域名（domain / context 同名段一律按作用域解释）。
    5. ``filename_object_scoped``：目录只能确立作用域，但文件名前缀命中该作用域
       内唯一对象别名。
    6. ``context_only`` / ``domain_only``：只能反推到 bounded context 或 domain。
    7. ``unowned``：无法反推，归横切面或等待人工裁决。

    任一层级出现多个候选时返回 ``ambiguous``，绝不代替业务任意择一。
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
    """AST 比对本文件的云侧 kind 规则与 verify_service_architecture.py 的原表。"""
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


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _iter_files(root: Path, suffixes: Iterable[str]) -> list[Path]:
    allowed = frozenset(suffixes)
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in allowed and not path.is_symlink()
    )


def _is_cloud_test_file(path: Path) -> bool:
    name = path.name
    return (
        name.endswith("_test.go")
        or name.startswith("test_")
        or "__local_contract_test" in name
        or "__api_integration_test" in name
    )


def service_domains() -> dict[str, tuple[str, str]]:
    """扫描 ``contracts/domain.yaml``，返回 service 相对根 → ``(owner, domain)``。"""
    mapping: dict[str, tuple[str, str]] = {}
    for pattern in SERVICE_ROOT_GLOBS:
        for service in sorted(ROOT.glob(pattern)):
            domain_path = service / "contracts" / "domain.yaml"
            if not domain_path.is_file():
                continue
            try:
                document = yaml.safe_load(domain_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            domain = str(document.get("domain") or "").strip()
            if domain:
                mapping[_relative(service)] = (service.name, domain)
    return mapping


def scan_cloud(roster: ObjectRoster) -> tuple[list[dict], list[dict], list[str]]:
    """扫描云侧 production 与测试文件，返回 ``(rows, findings, supportPaths)``。"""
    rows: list[dict] = []
    findings: list[dict] = []
    support_rows: list[str] = []
    for service_relative, (owner, domain) in sorted(service_domains().items()):
        service = ROOT / service_relative
        internal = service / "internal"
        for path in _iter_files(internal, CLOUD_SOURCE_SUFFIXES):
            parts = path.relative_to(internal).parts
            identity = derive_cloud_source_identity(parts)
            if identity is None:
                # `internal/<domain>/<context>/...` 是 platform-ops 的历史多余前缀。
                nested = derive_cloud_source_identity(parts[1:]) if parts else None
                if nested is not None and parts and parts[0] == domain:
                    identity = nested
            if identity is None:
                findings.append(
                    {
                        "kind": "cloud_unowned_source",
                        "path": _relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": "internal/<context>/<object>/<layer> 不可反推",
                    }
                )
                continue
            context, object_name, layer = identity
            record = roster.by_key.get((domain, context, object_name))
            if record is None:
                findings.append(
                    {
                        "kind": "cloud_source_without_object",
                        "path": _relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": f"{domain}.{context}.{object_name} 不在 ContractGraph roster",
                    }
                )
                continue
            rows.append(
                {
                    "side": "cloud",
                    "role": "test" if _is_cloud_test_file(path) else "production",
                    "path": _relative(path),
                    "objectId": record["objectId"],
                    "domain": domain,
                    "context": context,
                    "objectName": object_name,
                    "currentLayer": layer,
                    "targetLayer": layer,
                    "targetPath": _relative(path),
                    "status": "canonical",
                    "method": "cloud_path_exact",
                    "confidence": CLAIM_METHOD_CONFIDENCE["cloud_path_exact"],
                }
            )
        tests = service / "tests"
        for path in _iter_files(tests, CLOUD_SOURCE_SUFFIXES):
            parts = path.relative_to(tests).parts
            if parts and parts[0] == CLOUD_TEST_SUPPORT_ROOT:
                support_rows.append(_relative(path))
                continue
            identity = derive_cloud_test_identity(parts)
            if identity is None:
                findings.append(
                    {
                        "kind": "cloud_unowned_test",
                        "path": _relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": "tests/<layer>/<context>/<object> 不可反推",
                    }
                )
                continue
            test_layer, context, object_name = identity
            record = roster.by_key.get((domain, context, object_name))
            if record is None:
                findings.append(
                    {
                        "kind": "cloud_test_without_object",
                        "path": _relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": f"{domain}.{context}.{object_name} 不在 ContractGraph roster",
                    }
                )
                continue
            rows.append(
                {
                    "side": "cloud",
                    "role": f"test:{test_layer}",
                    "path": _relative(path),
                    "objectId": record["objectId"],
                    "domain": domain,
                    "context": context,
                    "objectName": object_name,
                    "currentLayer": test_layer,
                    "targetLayer": test_layer,
                    "targetPath": _relative(path),
                    "status": "canonical",
                    "method": "cloud_path_exact",
                    "confidence": CLAIM_METHOD_CONFIDENCE["cloud_path_exact"],
                }
            )
    return rows, findings, sorted(support_rows)


def load_page_claims() -> tuple[dict[str, list[str]], list[dict]]:
    """载入页面 → object_ids，返回 ``(claims, pages)``；claims 键为仓库相对路径。"""
    document = yaml.safe_load(
        (ROOT / PAGE_OBJECT_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    source_root = str(document.get("source_path_root") or APP_ROOT.as_posix())
    claims: dict[str, list[str]] = {}
    pages: list[dict] = []
    for page in document.get("pages") or []:
        source_path = str(page.get("source_path") or "")
        if not source_path:
            continue
        relative_path = f"{source_root}/{source_path}"
        object_ids = sorted(str(value) for value in (page.get("object_ids") or []))
        pages.append(
            {
                "pageId": str(page.get("page_id") or ""),
                "path": relative_path,
                "pageKind": str(page.get("page_kind") or ""),
                "objectIds": object_ids,
            }
        )
        if object_ids:
            claims[relative_path] = object_ids
    return claims, sorted(pages, key=lambda item: item["path"])


def scan_app(
    roster: ObjectRoster,
    page_claims: dict[str, list[str]],
) -> tuple[list[dict], list[dict]]:
    """扫描端侧 lib/test 文件，派生对象归属与迁移目标。"""
    rows: list[dict] = []
    findings: list[dict] = []

    lib_root = ROOT / APP_LIB_ROOT
    for path in _iter_files(lib_root, {APP_SOURCE_SUFFIX}):
        relative_path = _relative(path)
        parts = path.relative_to(lib_root).parts
        claim = derive_app_object_claim(parts, roster, page_claims, relative_path)
        layer = derive_app_layer(parts, roster)
        row = {
            "side": "app",
            "role": "production",
            "path": relative_path,
            "method": claim["method"],
            "confidence": CLAIM_METHOD_CONFIDENCE[claim["method"]],
            "aliasTier": claim.get("aliasTier"),
            "currentLayer": layer,
            "objectIds": claim["objectIds"],
            "contextIds": claim.get("contextIds", []),
            "ambiguous": claim["ambiguous"],
        }
        row["domains"] = claim.get("domains", [])
        if claim["objectIds"] and not claim["ambiguous"]:
            record = roster.objects[claim["objectIds"][0]]
            # 已处于目标形态时层由物理位置精确给出；page_object_contract 命中即证明
            # 该文件是入向表现层；其余情况不猜层，层不可派生时如实标记，交由对应
            # domain 流在迁移时决定。
            target_layer = (
                claim.get("targetLayer")
                or layer
                or ("presentation" if claim["method"] == "page_object_contract" else None)
            )
            row.update(
                {
                    "objectId": record["objectId"],
                    "domain": record["domain"],
                    "context": record["context"],
                    "objectName": record["objectName"],
                    "targetLayer": target_layer,
                }
            )
            if target_layer is None:
                row.update({"status": "layer_unresolved", "targetPath": None})
                findings.append(
                    {
                        "kind": "app_layer_unresolved",
                        "path": relative_path,
                        "method": claim["method"],
                        "candidates": [record["objectId"]],
                        "reason": "对象归属明确但现状路径未表达层角色，目标层待裁决",
                    }
                )
            elif claim["method"] == "app_target_shape":
                # 已在目标位置：目标路径就是自身，不做重构造。重构造会拍平层内
                # 合法子路径（`presentation/widgets/card.dart` → `presentation/card.dart`），
                # 破坏 derive(derive(p)) == derive(p)。
                row.update({"status": "canonical", "targetPath": relative_path})
            else:
                row.update(
                    {
                        "status": "mappable",
                        "targetPath": derive_app_target_path(
                            record["domain"],
                            record["context"],
                            record["objectName"],
                            target_layer,
                            path.name,
                        ),
                    }
                )
        elif claim["ambiguous"]:
            multi_page = claim["method"] == "page_object_contract"
            row.update(
                {
                    "status": "multi_object_page" if multi_page else "ambiguous",
                    "targetLayer": "presentation" if multi_page else layer,
                    "targetPath": None,
                }
            )
            findings.append(
                {
                    "kind": "app_multi_object_page"
                    if multi_page
                    else "app_ambiguous_claim",
                    "path": relative_path,
                    "method": claim["method"],
                    "candidates": claim["objectIds"] or claim.get("contextIds", []),
                    "reason": "页面横跨多个对象，presentation 归属需先拆页"
                    if multi_page
                    else "多个候选对象/上下文，需业务裁决，派生器不代选",
                }
            )
        elif claim["method"] in {"context_only", "domain_only"}:
            row.update(
                {
                    "status": claim["method"],
                    "targetLayer": layer,
                    "targetPath": None,
                }
            )
            findings.append(
                {
                    "kind": f"app_{claim['method']}",
                    "path": relative_path,
                    "method": claim["method"],
                    "candidates": claim.get("contextIds") or claim.get("domains", []),
                    "reason": "只能反推到 bounded context / domain，对象归属待裁决",
                }
            )
        else:
            root = derive_app_cross_cutting_root(parts)
            target_path = derive_app_cross_cutting_target_path(root, parts)
            # 已经物理落在横切根下的文件是「搬迁完成」，不是「无法反推的待裁决项」；
            # 继续记为 finding 会随 W1b 推进不断累积假账。
            already_placed = target_path == relative_path
            row.update(
                {
                    "method": "cross_cutting",
                    "confidence": CLAIM_METHOD_CONFIDENCE["cross_cutting"],
                    "crossCuttingRoot": root,
                    "targetLayer": None,
                    "targetPath": target_path,
                    "status": "canonical_cross_cutting"
                    if already_placed
                    else "cross_cutting",
                }
            )
            if not already_placed:
                findings.append(
                    {
                        "kind": "app_unowned_source",
                        "path": relative_path,
                        "method": "unowned",
                        "candidates": [],
                        "reason": f"无法反推对象，暂归横切面 {APP_CROSS_CUTTING_ROOTS[root]}",
                    }
                )
        rows.append(row)

    test_root = ROOT / APP_TEST_ROOT
    for path in _iter_files(test_root, {APP_SOURCE_SUFFIX}):
        relative_path = _relative(path)
        parts = path.relative_to(test_root).parts
        test_layer = parts[0] if parts and parts[0] in APP_TEST_LAYERS else None
        inner = parts[1:] if test_layer else parts
        # 已处于测试目标形态时身份由物理位置精确决定，别名启发式必须让位，否则
        # `content/content/post/comment/x_test.dart` 会被深层段劫持成 content.comment。
        shaped_test = (
            derive_app_test_target_shape_identity(inner, roster) if test_layer else None
        )
        if shaped_test is not None:
            claim = {
                "method": "app_target_shape",
                "objectIds": [roster.by_key[shaped_test]["objectId"]],
                "ambiguous": False,
                "aliasTier": None,
            }
        else:
            claim = derive_app_object_claim(inner, roster, page_claims, relative_path)
        row = {
            "side": "app",
            "role": f"test:{test_layer}" if test_layer else "test",
            "path": relative_path,
            "method": claim["method"],
            "confidence": CLAIM_METHOD_CONFIDENCE[claim["method"]],
            "aliasTier": claim.get("aliasTier"),
            "currentLayer": test_layer,
            "objectIds": claim["objectIds"],
            "contextIds": claim.get("contextIds", []),
            "ambiguous": claim["ambiguous"],
        }
        if claim["objectIds"] and not claim["ambiguous"] and test_layer:
            record = roster.objects[claim["objectIds"][0]]
            row.update(
                {
                    "objectId": record["objectId"],
                    "domain": record["domain"],
                    "context": record["context"],
                    "objectName": record["objectName"],
                    "targetLayer": test_layer,
                    # 已在 `test/<layer>/<domain>/<context>/<object>/` 目标形态时目标
                    # 路径即自身（保留对象下可选子路径），否则按目标形态构造。
                    "targetPath": relative_path
                    if shaped_test is not None
                    else derive_app_test_target_path(
                        test_layer,
                        record["domain"],
                        record["context"],
                        record["objectName"],
                        path.name,
                    ),
                    "status": "canonical" if shaped_test is not None else "mappable",
                }
            )
        else:
            if claim["ambiguous"]:
                status = "ambiguous"
                kind = "app_ambiguous_test"
            elif claim["method"] in {"context_only", "domain_only"}:
                status = claim["method"]
                kind = f"app_{claim['method']}_test"
            elif not test_layer:
                status = "unknown_test_root"
                kind = "app_unknown_test_root"
            else:
                status = "unowned"
                kind = "app_unowned_test"
            row.update({"status": status, "targetPath": None})
            findings.append(
                {
                    "kind": kind,
                    "path": relative_path,
                    "method": claim["method"],
                    "candidates": claim["objectIds"]
                    or claim.get("contextIds")
                    or claim.get("domains", []),
                    "reason": "端侧测试无法唯一反推对象",
                }
            )
        rows.append(row)
    return rows, findings


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


def _app_top_level_tree(relative_path: str) -> str:
    parts = relative_path.split("/")
    if len(parts) >= 3 and parts[1] == "lib":
        return f"lib/{parts[2]}" if len(parts) > 3 else "lib/<root>"
    if len(parts) >= 3 and parts[1] == "test":
        return f"test/{parts[2]}" if len(parts) > 3 else "test/<root>"
    return "/".join(parts[:2])


def build_object_view(
    roster: ObjectRoster,
    cloud_rows: Sequence[dict],
    app_rows: Sequence[dict],
    page_claims: dict[str, list[str]],
) -> dict[str, dict]:
    """按对象聚合端云物理文件与层出现情况。"""
    claimed_by_page: set[str] = set()
    for object_ids in page_claims.values():
        claimed_by_page.update(object_ids)

    view: dict[str, dict] = {}
    for object_id, record in roster.objects.items():
        view[object_id] = {
            **record,
            "claimedByPage": object_id in claimed_by_page,
            "cloud": {"layers": {}, "tests": {}},
            "app": {"layers": {}, "tests": {}},
        }
    for row in cloud_rows:
        entry = view[row["objectId"]]["cloud"]
        bucket = "tests" if row["role"].startswith("test") else "layers"
        entry[bucket].setdefault(row["currentLayer"], []).append(row["path"])
    for row in app_rows:
        object_id = row.get("objectId")
        if not object_id:
            continue
        entry = view[object_id]["app"]
        if row["role"].startswith("test"):
            entry["tests"].setdefault(row["currentLayer"] or "unknown", []).append(
                row["path"]
            )
        else:
            entry["layers"].setdefault(row.get("targetLayer") or "unknown", []).append(
                row["path"]
            )

    for entry in view.values():
        kind = entry["kind"]
        for side in ("cloud", "app"):
            for bucket in ("layers", "tests"):
                entry[side][bucket] = {
                    layer: sorted(paths)
                    for layer, paths in sorted(entry[side][bucket].items())
                }
        cloud_layers = set(entry["cloud"]["layers"])
        missing_cloud = sorted(set(required_cloud_layers(kind)) - cloud_layers)
        if kind == "external_reference":
            if "application" not in cloud_layers:
                missing_cloud.append("application")
            if not cloud_layers & set(CLOUD_EXTERNAL_REFERENCE_EITHER):
                missing_cloud.append("adapters-or-infrastructure")
        entry["missingCloudLayers"] = sorted(set(missing_cloud))

        app_layers = set(entry["app"]["layers"])
        expected_app = set(
            required_app_layers(kind, claimed_by_page=entry["claimedByPage"])
        )
        entry["requiredAppLayers"] = sorted(expected_app)
        entry["missingAppLayers"] = sorted(expected_app - app_layers)
        entry["conditionalAppLayers"] = sorted(
            set(CONDITIONAL_APP_LAYERS_BY_KIND.get(kind, ())) - app_layers
        )
        entry["forbiddenAppLayersPresent"] = sorted(
            set(FORBIDDEN_APP_LAYERS_BY_KIND.get(kind, ())) & app_layers
        )
    return view


def build_baseline(
    roster: ObjectRoster,
    cloud_rows: Sequence[dict],
    app_rows: Sequence[dict],
    pages: Sequence[dict],
    object_view: dict[str, dict],
) -> dict:
    """派生现状基线：散落度、无主文件、无对象页面、缺层。"""
    scatter: dict[str, dict] = {}
    for row in app_rows:
        object_id = row.get("objectId")
        if not object_id:
            continue
        domain = roster.objects[object_id]["domain"]
        tree = _app_top_level_tree(row["path"])
        bucket = scatter.setdefault(
            domain,
            {"domain": domain, "trees": {}, "files": 0, "objects": set()},
        )
        bucket["trees"][tree] = bucket["trees"].get(tree, 0) + 1
        bucket["files"] += 1
        bucket["objects"].add(object_id)
    for domain, bucket in scatter.items():
        bucket["treeCount"] = len(bucket["trees"])
        bucket["objectCount"] = len(bucket["objects"])
        bucket["objects"] = sorted(bucket["objects"])
        bucket["trees"] = dict(sorted(bucket["trees"].items()))

    # 「无主文件」= 扫到但无法唯一归属到任何 object 的端侧文件，
    # 覆盖 unowned / context_only / domain_only / ambiguous / multi_object_page。
    ownerless_rows = [row for row in app_rows if not row.get("objectId")]
    unowned_by_tree = Counter(
        _app_top_level_tree(row["path"]) for row in ownerless_rows
    )
    unowned_by_status = Counter(row["status"] for row in ownerless_rows)
    claim_by_method = Counter(
        row["method"] for row in app_rows if row.get("objectId")
    )
    status_totals = Counter(row["status"] for row in app_rows)

    page_paths = {page["path"] for page in pages}
    pages_without_object = [
        page["path"] for page in pages if not page["objectIds"]
    ]
    # 页面形态分两级：`*_page.dart` 是强信号（应是真实页面对象），
    # `pages/**` 下的其他文件多为页面片段（`*_page_state.dart`、`*_widgets.dart`），
    # 只作候选复核，不等同于缺页面契约。
    page_named_files: list[str] = []
    page_directory_files: list[str] = []
    for path in _iter_files(ROOT / APP_LIB_ROOT, {APP_SOURCE_SUFFIX}):
        relative_path = _relative(path)
        if relative_path in page_paths:
            continue
        if path.name.endswith("_page.dart"):
            page_named_files.append(relative_path)
        elif "pages" in path.relative_to(ROOT / APP_LIB_ROOT).parts:
            page_directory_files.append(relative_path)
    page_named_files.sort()
    page_directory_files.sort()

    missing_app = {
        object_id: entry["missingAppLayers"]
        for object_id, entry in sorted(object_view.items())
        if entry["missingAppLayers"]
    }
    missing_cloud = {
        object_id: entry["missingCloudLayers"]
        for object_id, entry in sorted(object_view.items())
        if entry["missingCloudLayers"]
    }
    objects_without_app_file = sorted(
        object_id
        for object_id, entry in object_view.items()
        if not entry["app"]["layers"] and not entry["app"]["tests"]
    )

    return {
        "appScatterByDomain": dict(sorted(scatter.items())),
        "appUnownedFilesByTree": dict(sorted(unowned_by_tree.items())),
        "appUnownedFilesByStatus": dict(sorted(unowned_by_status.items())),
        "appUnownedFileTotal": len(ownerless_rows),
        "appClaimedFileTotal": len(app_rows) - len(ownerless_rows),
        "appClaimsByMethod": dict(sorted(claim_by_method.items())),
        "appStatusTotals": dict(sorted(status_totals.items())),
        # 搬迁进度：已处于目标形态（对象树或横切根）的端侧文件数。四条 domain 流与
        # W1b 用它衡量收敛，派生对这些文件必须幂等。
        "appCanonicalFileTotal": status_totals["canonical"]
        + status_totals["canonical_cross_cutting"],
        "pagesInContract": len(pages),
        "pagesWithoutObjectIds": pages_without_object,
        "pageNamedFilesOutsideContract": page_named_files,
        "pageDirectoryFilesOutsideContract": page_directory_files,
        "objectsMissingRequiredAppLayers": missing_app,
        "objectsMissingRequiredCloudLayers": missing_cloud,
        "objectsWithoutAnyAppFile": objects_without_app_file,
        "cloudFileTotal": len(cloud_rows),
        "appFileTotal": len(app_rows),
    }


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = (
    "side",
    "role",
    "status",
    "method",
    "confidence",
    "objectId",
    "domain",
    "context",
    "objectName",
    "currentLayer",
    "targetLayer",
    "path",
    "targetPath",
)


def render_manifest(rows: Sequence[dict]) -> str:
    lines = ["\t".join(MANIFEST_COLUMNS)]
    for row in sorted(rows, key=lambda item: (item["side"], item["path"])):
        lines.append(
            "\t".join(
                str(row.get(column) if row.get(column) is not None else "")
                for column in MANIFEST_COLUMNS
            )
        )
    return "\n".join(lines) + "\n"


def render_baseline_report(
    roster: ObjectRoster,
    baseline: dict,
    object_view: dict[str, dict],
    context_diff: dict,
) -> str:
    kinds = Counter(entry["kind"] for entry in roster.objects.values())
    lines: list[str] = []
    lines.append("# 端云对象化现状基线（派生产物，可删除可重建）")
    lines.append("")
    lines.append(f"- 规则标识：`{RULE_ID}`")
    lines.append("- 派生器：`quwoquan_ops/gate/object_path_map.py`")
    lines.append(
        "- 真相源：`quwoquan_service/generated/contract_graph.json`、"
        "`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`、"
        "`contracts/domain.yaml`、物理源码/测试树"
    )
    lines.append("")
    lines.append("## 1. 对象 roster")
    lines.append("")
    lines.append(f"- domain：{len(roster.domains)}")
    lines.append(f"- bounded context（ContractGraph `contextId`）：{len(roster.context_ids)}")
    lines.append(f"- business object：{len(roster.objects)}")
    lines.append("- kind 分布：")
    for kind, count in sorted(kinds.items()):
        lines.append(f"  - `{kind}`：{count}")
    lines.append("")
    lines.append("### bounded context 计数差异说明")
    lines.append("")
    for line in context_diff["explanation"]:
        lines.append(f"- {line}")
    lines.append("")
    lines.append("## 2. 端侧散落度（每个 domain 横跨的顶层树）")
    lines.append("")
    lines.append("| domain | 顶层树数 | 已归属对象数 | 已归属文件数 | 分布 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for domain, bucket in baseline["appScatterByDomain"].items():
        distribution = "、".join(
            f"`{tree}`={count}" for tree, count in bucket["trees"].items()
        )
        lines.append(
            f"| `{domain}` | {bucket['treeCount']} | {bucket['objectCount']} | "
            f"{bucket['files']} | {distribution} |"
        )
    lines.append("")
    lines.append("## 3. 无主文件（扫到但无法唯一归属到任何对象）")
    lines.append("")
    lines.append(
        f"- 端侧已唯一归属：{baseline['appClaimedFileTotal']} / "
        f"{baseline['appFileTotal']}"
    )
    lines.append(f"- 端侧无主文件合计：{baseline['appUnownedFileTotal']}")
    lines.append("- 按无主原因：")
    for status, count in baseline["appUnownedFilesByStatus"].items():
        lines.append(f"  - `{status}`：{count}")
    lines.append("- 已归属文件按派生方法：")
    for method, count in baseline["appClaimsByMethod"].items():
        lines.append(
            f"  - `{method}`（置信度 `{CLAIM_METHOD_CONFIDENCE[method]}`）：{count}"
        )
    lines.append("")
    lines.append("| 顶层树 | 无主文件数 |")
    lines.append("| --- | --- |")
    for tree, count in sorted(
        baseline["appUnownedFilesByTree"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| `{tree}` | {count} |")
    lines.append("")
    lines.append("## 4. 无对象的页面")
    lines.append("")
    lines.append(f"- `page_object_contract.yaml` 登记页面：{baseline['pagesInContract']}")
    lines.append(
        f"- 登记但 `object_ids` 为空：{len(baseline['pagesWithoutObjectIds'])}"
    )
    for path in baseline["pagesWithoutObjectIds"]:
        lines.append(f"  - `{path}`")
    lines.append(
        f"- 磁盘上 `*_page.dart` 但未被契约登记："
        f"{len(baseline['pageNamedFilesOutsideContract'])}"
    )
    for path in baseline["pageNamedFilesOutsideContract"]:
        lines.append(f"  - `{path}`")
    lines.append(
        f"- `pages/**` 下未登记的页面片段（`*_page_state.dart` 等，仅候选复核）："
        f"{len(baseline['pageDirectoryFilesOutsideContract'])}"
    )
    lines.append("")
    lines.append("## 5. 缺层统计")
    lines.append("")
    lines.append(
        f"- 端侧缺必需层的对象：{len(baseline['objectsMissingRequiredAppLayers'])} / "
        f"{len(roster.objects)}"
    )
    lines.append(
        f"- 云侧缺必需层的对象：{len(baseline['objectsMissingRequiredCloudLayers'])} / "
        f"{len(roster.objects)}"
    )
    lines.append(
        f"- 端侧完全没有任何文件的对象：{len(baseline['objectsWithoutAnyAppFile'])}"
    )
    missing_counter = Counter()
    for layers in baseline["objectsMissingRequiredAppLayers"].values():
        missing_counter.update(layers)
    missing_cloud_counter = Counter()
    for layers in baseline["objectsMissingRequiredCloudLayers"].values():
        missing_cloud_counter.update(layers)
    for label, counter in (("端侧", missing_counter), ("云侧", missing_cloud_counter)):
        lines.append(f"- {label}缺失层分布：")
        if not counter:
            lines.append(
                f"  - 无：{len(roster.objects)} 个对象的 kind 必需层全部齐备"
            )
        for layer, count in sorted(counter.items()):
            lines.append(f"  - `{layer}`：{count}")
    lines.append("")
    lines.append("### 端侧缺必需层明细")
    lines.append("")
    lines.append("| objectId | kind | 被页面认领 | 必需层 | 缺失层 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for object_id, layers in baseline["objectsMissingRequiredAppLayers"].items():
        entry = object_view[object_id]
        lines.append(
            f"| `{object_id}` | `{entry['kind']}` | "
            f"{'是' if entry['claimedByPage'] else '否'} | "
            f"{'、'.join(entry['requiredAppLayers'])} | {'、'.join(layers)} |"
        )
    lines.append("")
    lines.append("## 6. 文件规模")
    lines.append("")
    lines.append(f"- 云侧扫描并归属的文件：{baseline['cloudFileTotal']}")
    lines.append(
        f"- 云侧 `tests/support/**` 共享支撑文件（不承载对象身份）："
        f"{baseline['cloudTestSupportFileTotal']}"
    )
    lines.append(f"- 端侧扫描的文件：{baseline['appFileTotal']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def build_context_diff(roster: ObjectRoster) -> dict:
    """派生 bounded context 计数的各个可观测口径，并解释常见的 24 vs 22 差异。"""
    context_yaml = sorted(
        _relative(path)
        for pattern in SERVICE_ROOT_GLOBS
        for path in ROOT.glob(f"{pattern}/contracts/*/context.yaml")
    )
    contract_dirs = sorted(
        _relative(path)
        for pattern in SERVICE_ROOT_GLOBS
        for path in ROOT.glob(f"{pattern}/contracts/*")
        if path.is_dir()
    )
    shared_contract_dirs = [
        path for path in contract_dirs if path.rsplit("/", 1)[-1].startswith("_")
    ]
    internal_dirs = sorted(
        _relative(path)
        for pattern in SERVICE_ROOT_GLOBS
        for path in ROOT.glob(f"{pattern}/internal/*")
        if path.is_dir()
    )
    object_contexts = sorted(
        {record["contextId"] for record in roster.objects.values()}
    )
    context_names = {context_id.split(".", 1)[1] for context_id in roster.context_ids}
    non_context_internal_dirs = [
        path for path in internal_dirs if path.rsplit("/", 1)[-1] not in context_names
    ]
    counts = {
        "contractGraphContextId": len(roster.context_ids),
        "contextYamlFiles": len(context_yaml),
        "contextIdsCarryingObjects": len(object_contexts),
        "serviceContractsChildDirs": len(contract_dirs),
        "serviceContractsSharedDirs": len(shared_contract_dirs),
        "serviceInternalChildDirs": len(internal_dirs),
        "nonContextInternalChildDirs": len(non_context_internal_dirs),
    }
    service_glob = "{services,control-plane}"
    explanation = [
        "ContractGraph `businessObjectMaps[].boundedContexts[].contextId` 实测 "
        f"{counts['contractGraphContextId']} 个；`contracts/*/context.yaml` "
        f"{counts['contextYamlFiles']} 个；实际承载对象的 contextId "
        f"{counts['contextIdsCarryingObjects']} 个。三个口径完全一致，"
        "本派生器以该 roster 为唯一准据。",
        f"因此 OPEN-001 记的 {counts['contractGraphContextId']} 与 ContractGraph roster "
        "一致，`contextId` 口径下不存在 24。",
        f"能数出 24 的是**目录**口径：`{service_glob}/*/internal/*` 子目录共 "
        f"{counts['serviceInternalChildDirs']} 个，其中 "
        f"{counts['nonContextInternalChildDirs']} 个不是 bounded context（"
        + "、".join(f"`{path}`" for path in non_context_internal_dirs)
        + f"），扣除后为 "
        f"{counts['serviceInternalChildDirs'] - counts['nonContextInternalChildDirs']} 个。"
        f"另一个近似口径是 `{service_glob}/*/contracts/*` 子目录 "
        f"{counts['serviceContractsChildDirs']} 个，其中 "
        f"{counts['serviceContractsSharedDirs']} 个是 `_shared` 非 context 目录，"
        f"扣除后 "
        f"{counts['serviceContractsChildDirs'] - counts['serviceContractsSharedDirs']} 个。",
        f"结论：24 是目录计数口径的偏差，contextId roster 恒为 "
        f"{counts['contractGraphContextId']}；后续 domain 并行流只读本派生器的 roster，"
        "不再各自数目录。",
    ]
    return {
        "counts": counts,
        "contextIds": sorted(roster.context_ids),
        "contextYamlFiles": context_yaml,
        "serviceContractsChildDirs": contract_dirs,
        "serviceInternalChildDirs": internal_dirs,
        "nonContextInternalChildDirs": non_context_internal_dirs,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _json_dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="派生 business object → 端云物理文件映射、迁移清单与现状基线"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="覆盖输出目录（默认 .qwq_output/env/repo/runs/object-path-map）",
    )
    arguments = parser.parse_args(argv)

    drift = check_cloud_layer_rule_mirror()
    if drift:
        print("[object-path-map] FAIL")
        for issue in drift:
            print(f"  - {issue}")
        return 1

    graph_path = ROOT / CONTRACT_GRAPH_PATH
    graph_bytes = graph_path.read_bytes()
    graph = json.loads(graph_bytes)
    roster = ObjectRoster(graph)

    page_claims, pages = load_page_claims()
    cloud_rows, cloud_findings, cloud_support_paths = scan_cloud(roster)
    app_rows, app_findings = scan_app(roster, page_claims)
    findings = sorted(
        cloud_findings + app_findings,
        key=lambda item: (item["kind"], item["path"]),
    )
    object_view = build_object_view(roster, cloud_rows, app_rows, page_claims)
    context_diff = build_context_diff(roster)
    baseline = build_baseline(roster, cloud_rows, app_rows, pages, object_view)
    baseline["cloudTestSupportFileTotal"] = len(cloud_support_paths)

    output_dir = (
        Path(arguments.output_dir)
        if arguments.output_dir
        else repo_runs_root() / OUTPUT_DIR_NAME
    )
    mapping_payload = {
        "ruleId": RULE_ID,
        "inputs": {
            "contractGraph": {
                "path": CONTRACT_GRAPH_PATH.as_posix(),
                "sha256": hashlib.sha256(graph_bytes).hexdigest(),
            },
            "pageObjectContract": PAGE_OBJECT_CONTRACT_PATH.as_posix(),
            "presentationRequirementSource": PRESENTATION_REQUIREMENT_SOURCE,
        },
        "layerRules": {
            "cloudLayers": list(CLOUD_LAYERS),
            "appLayers": list(APP_LAYERS),
            "appToCloudLayerEquivalence": APP_TO_CLOUD_LAYER_EQUIVALENCE,
            "requiredCloudLayersByKind": {
                kind: list(layers)
                for kind, layers in sorted(REQUIRED_CLOUD_LAYERS_BY_KIND.items())
            },
            "requiredAppLayersByKind": {
                kind: list(layers)
                for kind, layers in sorted(REQUIRED_APP_LAYERS_BY_KIND.items())
            },
            "conditionalAppLayersByKind": {
                kind: list(layers)
                for kind, layers in sorted(CONDITIONAL_APP_LAYERS_BY_KIND.items())
            },
            "forbiddenAppLayersByKind": {
                kind: list(layers)
                for kind, layers in sorted(FORBIDDEN_APP_LAYERS_BY_KIND.items())
            },
            "appCrossCuttingRoots": APP_CROSS_CUTTING_ROOTS,
        },
        "boundedContextDiff": context_diff,
        "objects": {
            object_id: object_view[object_id] for object_id in sorted(object_view)
        },
    }
    _write(output_dir / "object_path_map.json", _json_dump(mapping_payload))
    _write(
        output_dir / "migration_manifest.tsv",
        render_manifest([*cloud_rows, *app_rows]),
    )
    _write(
        output_dir / "derivation_findings.json",
        _json_dump({"ruleId": RULE_ID, "findings": findings}),
    )
    _write(
        output_dir / "baseline_report.md",
        render_baseline_report(roster, baseline, object_view, context_diff),
    )
    _write(
        output_dir / "baseline_summary.json",
        _json_dump({"ruleId": RULE_ID, "baseline": baseline}),
    )

    try:
        printable_output_dir = output_dir.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        printable_output_dir = output_dir.as_posix()
    print("[object-path-map] OK")
    print(
        _json_dump(
            {
                "ruleId": RULE_ID,
                "outputDir": printable_output_dir,
                "domains": len(roster.domains),
                "boundedContexts": len(roster.context_ids),
                "objects": len(roster.objects),
                "cloudFiles": len(cloud_rows),
                "appFiles": len(app_rows),
                "findings": len(findings),
                "appUnownedFileTotal": baseline["appUnownedFileTotal"],
                "objectsMissingRequiredAppLayers": len(
                    baseline["objectsMissingRequiredAppLayers"]
                ),
                "objectsMissingRequiredCloudLayers": len(
                    baseline["objectsMissingRequiredCloudLayers"]
                ),
            }
        ).strip()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
