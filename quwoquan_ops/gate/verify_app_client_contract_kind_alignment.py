#!/usr/bin/env python3
"""端侧 kind 义务门禁：让 App 按云侧对象 kind 承担义务，而不是只看 ``clientContract``。

背景
----
云侧对象 kind 治理是完整的：``access.commands`` / ``identity.version_source`` /
``required_layers`` / runtime entrypoint 全部由 ``object.yaml`` 的 ``kind`` 派生，并有
``verify_service_architecture.py`` 等多重门禁。端侧长期是 **kind-agnostic** 的——层与
port 只由「``clientContract`` 是否存在」与「页面物理 owner」派生
（见 ``object_path_map.APP_OPERATION_REQUIRED_LAYERS`` /
``APP_PAGE_OWNER_REQUIRED_LAYERS``），唯一的 kind 约束是
``object_path_map.FORBIDDEN_APP_LAYERS_BY_KIND``。

「云强端弱」会让端侧把只读或只追加的对象当成可变聚合消费，而云侧完全看不到：

* ``append_only_fact`` 被端侧接上聚合形状的 ``*CommandWriter``，读起来像可 update；
* ``runtime_session`` 拥有 presentation / 被登记成页面物理 owner，像持久业务对象；
* ``projection`` 通过端侧本地可变 patch 路径成为第二真相源，绕过 projection 的
  最终一致读模型；
* ``external_reference`` 建立本地 authoritative 持久化，绕过
  ``provider_read_through_without_local_authoritative_state``。

本门禁把这四类义务变成可执行判据。

真相源（只读）
--------------
1. ``quwoquan_service/generated/contract_graph.json``
   对象 kind 与 ``operations[].{objectId,kind,clientContract}``。
2. ``quwoquan_service/services/*/contracts/**/object.yaml`` 与
   ``quwoquan_service/control-plane/*/contracts/**/object.yaml``
   的 ``access.commands``。这是云侧「谁能写这个对象」的唯一声明。
3. ``quwoquan_ops/gate/object_path_map.py``
   对象归属、端侧层、页面物理 owner。本门禁不实现第二套路径反推规则。

校验规则
--------
K1 ``client_operation_kind_vs_access_commands``
    每个对象的 ``access.commands`` 必须由 kind 派生（``ACCESS_COMMANDS_BY_KIND``），
    且它的 clientContract operation kind 必须落在该 ``access.commands`` 允许的集合内
    （``CLIENT_OPERATION_KINDS_BY_ACCESS_COMMANDS``）。

K2 ``readonly_kind_client_command_count``
    ``projection`` 与 ``external_reference``（``access.commands: none``）的
    client command 数必须为 0。

K3 ``append_only_fact_append_port_shape``
    ``append_only_fact`` 的端侧 port 不得使用聚合形状的 ``*CommandWriter``
    （必须用 ``APP_APPEND_PORT_NAMING`` 的 append port，与聚合类型可区分），
    也不得在 ``application/**`` 声明 update / mutate 语义方法。

K4a ``forbidden_app_layer_for_kind``
    kind 禁止层（``object_path_map.FORBIDDEN_APP_LAYERS_BY_KIND`` 的镜像）：
    ``append_only_fact`` / ``runtime_session`` 不得拥有 ``presentation``，
    ``external_reference`` 不得拥有 ``domain`` / ``presentation``。

K4b ``runtime_session_app_shape``
    ``runtime_session`` 不得是页面物理 owner（PageOwned）。需要展示会话状态时，
    由某个业务对象的 presentation 消费 session 的公开 query port，而不是让 session
    自己成页。

K5 ``projection_local_mutation_path``
    ``projection`` 的端侧不得声明独立 command port，也不得暴露逐字段本地 patch
    路径。本地缓存只允许是「远端读结果的只读快照」加易失展示叠加层。

K6 ``external_reference_local_authoritative_state``
    ``external_reference`` 的端侧不得绑定本地 authoritative 持久化
    （Hive / SharedPreferences / sqflite / 耐久队列存储）。

没有 baseline、没有 allowlist：任何实测违规直接 BLOCK。缩小扫描范围同样会 BLOCK
（K0 前置校验：扫描根必须存在，且实测对象数必须为正）。

用法
----
    python3 quwoquan_ops/gate/verify_app_client_contract_kind_alignment.py
    python3 quwoquan_ops/gate/verify_app_client_contract_kind_alignment.py --kind projection
    python3 quwoquan_ops/gate/verify_app_client_contract_kind_alignment.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm

RULE_ID = "app-client-contract-kind-alignment/v1"

#: 云侧 ``object.yaml`` 中 ``access.commands`` 与 ``kind`` 的派生关系。
#:
#: 这是 ``quwoquan_service/**/contracts/**/object.yaml`` 的实测镜像：kind 决定谁能写
#: 该对象。端侧必须消费同一张表，否则端云会各自解释「这个对象能不能被写」。
ACCESS_COMMANDS_BY_KIND = {
    "aggregate_root": "aggregate_facade",
    "append_only_fact": "append_only_sink",
    "external_reference": "none",
    "process_manager": "process_facade",
    "projection": "none",
    "runtime_session": "session_facade",
}

#: ``access.commands`` 允许的 clientContract operation kind。
#:
#: ``none`` 只读；``append_only_sink`` 的 command 只表达一次追加；``session_facade``
#: 的写面是 session 生命周期而不是聚合命令，因此不允许 ``command``。
CLIENT_OPERATION_KINDS_BY_ACCESS_COMMANDS = {
    "aggregate_facade": frozenset({"command", "query"}),
    "append_only_sink": frozenset({"command", "query"}),
    "none": frozenset({"query"}),
    "process_facade": frozenset({"command", "query"}),
    "session_facade": frozenset({"query", "session"}),
}

#: ``access.commands: none`` 的两个 kind：端侧 client command 数必须为 0。
READONLY_KINDS = ("external_reference", "projection")

#: 端侧 append port 命名规范（``append_only_fact`` 专用）。
#:
#: 事实只追加、不更新，因此它的端侧写面必须与聚合写面**类型上可区分**：聚合命令要么
#: 成功要么失败并改变聚合状态，追加只是投递一条不可变事实。共用 ``*CommandWriter``
#: 会让调用方以为可以 update 一条已追加的事实。
APP_APPEND_PORT_NAMING = {
    "appender": "*FactAppender",
    "query": "*FactQuery",
    "forbiddenSharedWithAggregate": "*CommandWriter",
}

#: 端侧 session port 命名规范（``runtime_session`` 专用）。
#:
#: session 只在连接/请求期间存在，不是持久聚合，因此它没有 presentation、不成页；
#: 需要展示会话状态的页面消费它的公开 query port。
APP_SESSION_PORT_NAMING = {
    "facade": "*SessionFacade",
    "query": "*SessionQuery",
    "forbiddenLayers": ("presentation",),
    "forbiddenPageOwnership": True,
}

#: ``object_path_map.FORBIDDEN_APP_LAYERS_BY_KIND`` 的镜像。
#:
#: 端侧禁止层的唯一真相源是派生器；这里显式镜像出来，由配套 local_contract 断言两处
#: 不漂移。派生器负责「层是否存在」，本门禁负责 port 形状与 PageOwned 等无法用层表达
#: 的 kind 义务。
KIND_FORBIDDEN_APP_LAYERS_MIRROR = {
    "append_only_fact": ("presentation",),
    "external_reference": ("domain", "presentation"),
    "runtime_session": ("presentation",),
}

#: 聚合形状写面后缀：出现在只读/只追加对象上即为 kind 漂移。
AGGREGATE_COMMAND_PORT_SUFFIXES = ("CommandWriter", "CommandFacade")

#: projection 上禁止的写面后缀。projection 在端侧只有 query/reader。
PROJECTION_FORBIDDEN_PORT_SUFFIXES = (
    "CommandWriter",
    "CommandFacade",
    "Appender",
    "AppendFacet",
)

#: Dart 抽象 port 声明。端侧 typed port 一律是 ``abstract [interface] class``。
ABSTRACT_PORT_RE = re.compile(
    r"^\s*abstract\s+(?:interface\s+|mixin\s+|base\s+|final\s+|sealed\s+)*class\s+(\w+)",
    re.MULTILINE,
)

#: port 内的方法签名。缩进 >= 2 排除顶层函数；``(`` 排除字段与 getter。
PORT_METHOD_RE = re.compile(
    r"^\s{2,}(?:[\w<>?,.\s\[\]]+?\s+)?(\w+)\s*\(",
    re.MULTILINE,
)

#: ``append_only_fact`` 上禁止的方法语义前缀：事实不可更新。
FACT_MUTATION_METHOD_PREFIXES = (
    "update",
    "mutate",
    "patch",
    "edit",
    "modify",
    "rewrite",
    "overwrite",
)

#: ``projection`` 上禁止的方法语义前缀：只允许整体安装远端读结果快照，
#: 不允许逐字段本地 patch 让本地缓存变成第二真相源。
PROJECTION_MUTATION_METHOD_PREFIXES = ("patch",)

#: 方法名尾缀白名单：订阅/回调注册不是数据写入。
NON_DATA_METHOD_SUFFIXES = ("Listener", "Observer", "Callback", "Subscription")

#: 本地 authoritative 持久化标识（``external_reference`` 专用）。
LOCAL_AUTHORITATIVE_PERSISTENCE_MARKERS = (
    "package:hive",
    "package:hive_flutter",
    "Hive.openBox",
    "SharedPreferences",
    "package:sqflite",
    "ActorQueueStorage",
)


class GateInputError(RuntimeError):
    """扫描根缺失或输入不可解析：门禁必须失败，不得静默缩小范围。"""


@dataclass(frozen=True)
class AppFile:
    """一个被某对象认领的端侧生产文件。"""

    path: str
    layer: str | None
    text: str

    @property
    def is_public_seam(self) -> bool:
        return "/application/public/" in self.path


@dataclass(frozen=True)
class ObjectFacts:
    """单个对象的端云对齐事实。测试可直接构造，无需文件系统。"""

    object_id: str
    kind: str
    access_commands: str
    client_operation_kinds: Mapping[str, int] = field(default_factory=dict)
    app_files: tuple[AppFile, ...] = ()
    owns_page: bool = False
    page_paths: tuple[str, ...] = ()

    def client_command_count(self) -> int:
        return int(self.client_operation_kinds.get("command", 0))

    def app_layers(self) -> set[str]:
        return {item.layer for item in self.app_files if item.layer}


@dataclass(frozen=True)
class Violation:
    rule: str
    object_id: str
    kind: str
    detail: str
    evidence: str

    def render(self) -> str:
        return (
            f"[{self.rule}] {self.object_id} (kind={self.kind}): "
            f"{self.detail} @ {self.evidence}"
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "objectId": self.object_id,
            "kind": self.kind,
            "detail": self.detail,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# 判据
# ---------------------------------------------------------------------------


def _declared_ports(item: AppFile) -> list[str]:
    return ABSTRACT_PORT_RE.findall(item.text)


def _port_methods(item: AppFile) -> list[str]:
    names: list[str] = []
    for name in PORT_METHOD_RE.findall(item.text):
        if name.endswith(NON_DATA_METHOD_SUFFIXES):
            continue
        names.append(name)
    return names


def _mutation_methods(item: AppFile, prefixes: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for name in _port_methods(item):
        for prefix in prefixes:
            rest = name[len(prefix) :]
            if name.startswith(prefix) and rest[:1].isupper():
                hits.append(name)
                break
    return hits


def _check_access_commands_derivation(facts: ObjectFacts) -> list[Violation]:
    expected = ACCESS_COMMANDS_BY_KIND.get(facts.kind)
    if expected is None:
        return [
            Violation(
                rule="client_operation_kind_vs_access_commands",
                object_id=facts.object_id,
                kind=facts.kind,
                detail=(
                    "未登记的 object kind；先在 ACCESS_COMMANDS_BY_KIND 声明该 kind 的"
                    "写面语义，再让端侧消费"
                ),
                evidence="ACCESS_COMMANDS_BY_KIND",
            )
        ]
    if facts.access_commands != expected:
        return [
            Violation(
                rule="client_operation_kind_vs_access_commands",
                object_id=facts.object_id,
                kind=facts.kind,
                detail=(
                    f"access.commands={facts.access_commands!r} 与 kind 派生值 "
                    f"{expected!r} 漂移"
                ),
                evidence="object.yaml#access.commands",
            )
        ]
    return []


def _check_client_operation_kinds(facts: ObjectFacts) -> list[Violation]:
    allowed = CLIENT_OPERATION_KINDS_BY_ACCESS_COMMANDS.get(facts.access_commands)
    if allowed is None:
        return [
            Violation(
                rule="client_operation_kind_vs_access_commands",
                object_id=facts.object_id,
                kind=facts.kind,
                detail=(
                    f"未登记的 access.commands={facts.access_commands!r}；"
                    "先声明它允许的 client operation kind"
                ),
                evidence="CLIENT_OPERATION_KINDS_BY_ACCESS_COMMANDS",
            )
        ]
    violations: list[Violation] = []
    for operation_kind, count in sorted(facts.client_operation_kinds.items()):
        if count <= 0 or operation_kind in allowed:
            continue
        violations.append(
            Violation(
                rule="client_operation_kind_vs_access_commands",
                object_id=facts.object_id,
                kind=facts.kind,
                detail=(
                    f"{count} 个 clientContract operation kind={operation_kind!r} 不在 "
                    f"access.commands={facts.access_commands!r} 允许集合 "
                    f"{sorted(allowed)} 内"
                ),
                evidence="contract_graph.json#operations[].clientContract",
            )
        )
    return violations


def _check_readonly_client_commands(facts: ObjectFacts) -> list[Violation]:
    if facts.kind not in READONLY_KINDS:
        return []
    count = facts.client_command_count()
    if count == 0:
        return []
    return [
        Violation(
            rule="readonly_kind_client_command_count",
            object_id=facts.object_id,
            kind=facts.kind,
            detail=(
                f"只读 kind 的 client command 数必须为 0，实测 {count}；"
                "写入必须经拥有该状态的 aggregate command，再重新读取"
            ),
            evidence="contract_graph.json#operations[].clientContract",
        )
    ]


def _check_append_only_fact_ports(facts: ObjectFacts) -> list[Violation]:
    if facts.kind != "append_only_fact":
        return []
    violations: list[Violation] = []
    for item in facts.app_files:
        for port in _declared_ports(item):
            if port.endswith(AGGREGATE_COMMAND_PORT_SUFFIXES):
                violations.append(
                    Violation(
                        rule="append_only_fact_append_port_shape",
                        object_id=facts.object_id,
                        kind=facts.kind,
                        detail=(
                            f"port {port!r} 使用聚合写面形状；append_only_fact 必须用 "
                            f"{APP_APPEND_PORT_NAMING['appender']}，与聚合的 "
                            f"{APP_APPEND_PORT_NAMING['forbiddenSharedWithAggregate']} "
                            "类型上可区分"
                        ),
                        evidence=item.path,
                    )
                )
        if item.layer != "application":
            continue
        for name in _mutation_methods(item, FACT_MUTATION_METHOD_PREFIXES):
            violations.append(
                Violation(
                    rule="append_only_fact_append_port_shape",
                    object_id=facts.object_id,
                    kind=facts.kind,
                    detail=(
                        f"方法 {name!r} 表达 update/mutate 语义；事实不可更新，"
                        "只能追加新事实"
                    ),
                    evidence=item.path,
                )
            )
    return violations


#: 每个 kind 被禁止层的整改方向。层本身不解释「为什么」，这里补上。
FORBIDDEN_LAYER_REMEDY = {
    ("append_only_fact", "presentation"): (
        "事实流不直接成页；展示由消费该事实的业务对象 presentation 承担"
    ),
    ("external_reference", "domain"): (
        "external_reference 没有端侧不变式：刷新语义是 provider read-through "
        "without local authoritative state"
    ),
    ("external_reference", "presentation"): (
        "external_reference 不拥有页面；展示外部引用的页面归发起它的业务对象"
    ),
    ("runtime_session", "presentation"): (
        "session 只在连接/请求期间存在，不是持久业务聚合；展示会话状态应由某个业务"
        "对象的 presentation 消费 session 的公开 query port"
    ),
}


def _check_forbidden_app_layers(facts: ObjectFacts) -> list[Violation]:
    forbidden = set(KIND_FORBIDDEN_APP_LAYERS_MIRROR.get(facts.kind, ()))
    if not forbidden:
        return []
    violations: list[Violation] = []
    for item in facts.app_files:
        if item.layer not in forbidden:
            continue
        remedy = FORBIDDEN_LAYER_REMEDY.get((facts.kind, item.layer), "")
        violations.append(
            Violation(
                rule="forbidden_app_layer_for_kind",
                object_id=facts.object_id,
                kind=facts.kind,
                detail=f"kind 禁止 {item.layer!r} 层：{remedy}",
                evidence=item.path,
            )
        )
    return violations


def _check_runtime_session_shape(facts: ObjectFacts) -> list[Violation]:
    if facts.kind != "runtime_session":
        return []
    violations: list[Violation] = []
    if facts.owns_page:
        violations.append(
            Violation(
                rule="runtime_session_app_shape",
                object_id=facts.object_id,
                kind=facts.kind,
                detail=(
                    "runtime_session 被登记为页面物理 owner（PageOwned）；"
                    "session 不是持久业务对象，不得成页"
                ),
                evidence=", ".join(facts.page_paths) or opm.PRESENTATION_REQUIREMENT_SOURCE,
            )
        )
    return violations


def _check_projection_local_mutation(facts: ObjectFacts) -> list[Violation]:
    if facts.kind != "projection":
        return []
    violations: list[Violation] = []
    for item in facts.app_files:
        for port in _declared_ports(item):
            if port.endswith(PROJECTION_FORBIDDEN_PORT_SUFFIXES):
                violations.append(
                    Violation(
                        rule="projection_local_mutation_path",
                        object_id=facts.object_id,
                        kind=facts.kind,
                        detail=(
                            f"port {port!r} 是写面；projection 的 access.commands 为 "
                            "none，端侧只能有 query/reader"
                        ),
                        evidence=item.path,
                    )
                )
        if item.layer != "application":
            continue
        for name in _mutation_methods(item, PROJECTION_MUTATION_METHOD_PREFIXES):
            violations.append(
                Violation(
                    rule="projection_local_mutation_path",
                    object_id=facts.object_id,
                    kind=facts.kind,
                    detail=(
                        f"方法 {name!r} 是逐字段本地 patch 路径，会让本地缓存成为第二"
                        "真相源；本地缓存只能是远端读结果的只读快照，即时反馈用易失"
                        "展示叠加层表达"
                    ),
                    evidence=item.path,
                )
            )
    return violations


def _check_external_reference_local_state(facts: ObjectFacts) -> list[Violation]:
    if facts.kind != "external_reference":
        return []
    violations: list[Violation] = []
    for item in facts.app_files:
        for marker in LOCAL_AUTHORITATIVE_PERSISTENCE_MARKERS:
            if marker in item.text:
                violations.append(
                    Violation(
                        rule="external_reference_local_authoritative_state",
                        object_id=facts.object_id,
                        kind=facts.kind,
                        detail=(
                            f"绑定本地持久化 {marker!r}；external_reference 的刷新语义是 "
                            "provider read-through without local authoritative state，"
                            "端侧不得建立本地权威副本"
                        ),
                        evidence=item.path,
                    )
                )
    return violations


CHECKS = (
    _check_access_commands_derivation,
    _check_client_operation_kinds,
    _check_readonly_client_commands,
    _check_forbidden_app_layers,
    _check_append_only_fact_ports,
    _check_runtime_session_shape,
    _check_projection_local_mutation,
    _check_external_reference_local_state,
)


def evaluate(objects: Sequence[ObjectFacts]) -> list[Violation]:
    """对 *objects* 求值全部规则。空输入本身即为违规（防缩小扫描范围）。"""
    if not objects:
        return [
            Violation(
                rule="scan_scope",
                object_id="-",
                kind="-",
                detail=(
                    "实测对象数为 0；门禁不接受空扫描结果，请修复 ContractGraph 或"
                    "扫描根，不要缩小范围"
                ),
                evidence=opm.CONTRACT_GRAPH_PATH.as_posix(),
            )
        ]
    violations: list[Violation] = []
    for facts in objects:
        for check in CHECKS:
            violations.extend(check(facts))
    return sorted(
        violations,
        key=lambda item: (item.rule, item.object_id, item.evidence, item.detail),
    )


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------


def load_access_commands(repo_root: Path) -> dict[str, str]:
    """从 ``object.yaml`` 采集 ``<context>/<object>`` → ``access.commands``。"""
    roots = (
        repo_root / "quwoquan_service/services",
        repo_root / "quwoquan_service/control-plane",
    )
    missing = [root.as_posix() for root in roots if not root.is_dir()]
    if missing:
        raise GateInputError(f"云侧 contracts 扫描根缺失: {', '.join(missing)}")
    access: dict[str, str] = {}
    for root in roots:
        for path in sorted(root.glob("*/contracts/*/*/object.yaml")):
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as error:
                raise GateInputError(f"无法解析 {path}: {error}") from error
            if not isinstance(document, dict):
                continue
            block = document.get("access")
            commands = ""
            if isinstance(block, dict):
                commands = str(block.get("commands") or "")
            context = path.parent.parent.name
            access[f"{context}/{path.parent.name}"] = commands
    return access


def collect(repo_root: Path | None = None) -> list[ObjectFacts]:
    """从真实仓库采集 ``ObjectFacts``。扫描根缺失时抛 :class:`GateInputError`。"""
    repo_root = (repo_root or ROOT).resolve()
    graph_path = repo_root / opm.CONTRACT_GRAPH_PATH
    if not graph_path.is_file():
        raise GateInputError(f"ContractGraph 缺失: {graph_path.as_posix()}")
    lib_root = repo_root / opm.APP_LIB_ROOT
    if not lib_root.is_dir():
        raise GateInputError(f"端侧扫描根缺失: {lib_root.as_posix()}")

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    roster = opm.ObjectRoster(graph)
    access_by_scope = load_access_commands(repo_root)

    operation_kinds: dict[str, dict[str, int]] = {}
    for operation in graph.get("operations") or []:
        object_id = str(operation.get("objectId") or "")
        if object_id not in roster.objects or not operation.get("clientContract"):
            continue
        bucket = operation_kinds.setdefault(object_id, {})
        operation_kind = str(operation.get("kind") or "")
        bucket[operation_kind] = bucket.get(operation_kind, 0) + 1

    page_claims, pages = opm.load_page_claims()
    page_owners: dict[str, list[str]] = {}
    for page in pages:
        owner = opm.derive_page_physical_owner(page["path"], roster)
        if owner:
            page_owners.setdefault(owner, []).append(page["path"])

    app_rows, _ = opm.scan_app(roster, page_claims)
    lib_prefix = f"{opm.APP_LIB_ROOT.as_posix()}/"
    files_by_object: dict[str, list[AppFile]] = {}
    for row in app_rows:
        object_id = row.get("objectId")
        path = str(row.get("path") or "")
        if not object_id or row.get("ambiguous") or not path.startswith(lib_prefix):
            continue
        files_by_object.setdefault(object_id, []).append(
            AppFile(
                path=path,
                layer=row.get("currentLayer"),
                text=(repo_root / path).read_text(encoding="utf-8", errors="replace"),
            )
        )

    facts: list[ObjectFacts] = []
    for object_id, record in sorted(roster.objects.items()):
        scope = f"{record['context']}/{record['objectName']}"
        facts.append(
            ObjectFacts(
                object_id=object_id,
                kind=record["kind"],
                access_commands=access_by_scope.get(scope, ""),
                client_operation_kinds=operation_kinds.get(object_id, {}),
                app_files=tuple(
                    sorted(files_by_object.get(object_id, ()), key=lambda i: i.path)
                ),
                owns_page=object_id in page_owners,
                page_paths=tuple(sorted(page_owners.get(object_id, ()))),
            )
        )
    return facts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _summary(objects: Sequence[ObjectFacts]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for facts in objects:
        counts[facts.kind] = counts.get(facts.kind, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--kind",
        action="append",
        default=None,
        help="只求值指定 object kind（可重复）；默认全部",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    arguments = parser.parse_args(argv)

    try:
        objects = collect()
    except GateInputError as error:
        print(f"[{RULE_ID}] BLOCK: {error}", file=sys.stderr)
        return 1

    selected: Iterable[ObjectFacts] = objects
    if arguments.kind:
        wanted = set(arguments.kind)
        unknown = wanted - set(ACCESS_COMMANDS_BY_KIND)
        if unknown:
            print(
                f"[{RULE_ID}] BLOCK: 未知 kind {sorted(unknown)}",
                file=sys.stderr,
            )
            return 1
        selected = [facts for facts in objects if facts.kind in wanted]

    selected = list(selected)
    violations = evaluate(selected)

    if arguments.json:
        print(
            json.dumps(
                {
                    "ruleId": RULE_ID,
                    "scannedObjects": len(selected),
                    "objectsByKind": _summary(selected),
                    "violations": [item.as_dict() for item in violations],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            f"[{RULE_ID}] scanned {len(selected)} objects "
            f"({_summary(selected)})"
        )
        for item in violations:
            print(f"  {item.render()}")

    if violations:
        print(
            f"[{RULE_ID}] BLOCK: {len(violations)} kind alignment violation(s)",
            file=sys.stderr,
        )
        return 1
    print(f"[{RULE_ID}] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
