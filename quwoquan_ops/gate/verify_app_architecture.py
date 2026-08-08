#!/usr/bin/env python3
"""端侧对象化架构门禁 v1，云侧 `verify_service_architecture.py` 的对等物。

目标形态（与云侧 DDD 同构，层名等价见
`object_path_map.APP_TO_CLOUD_LAYER_EQUIVALENCE`）：

    quwoquan_app/lib/
    ├─ service/<service>/<context>/<object>/{domain,application,adapters,presentation}/
    ├─ runtime/        # 唯一公共 runtime 横切面（transport/codec/errors/config/auth/
    │                  # di/observability/platform/shell）
    ├─ design_system/  # 唯一设计系统横切面
    └─ l10n/           # flutter gen-l10n 的 arb 根，取自 quwoquan_app/l10n.yaml

三个非 service 根都是 `object_path_map.APP_CROSS_CUTTING_ROOTS` 的成员：顶层白名单
与派生器的横切根是同一份集合，不存在「合法顶层但派生器认为待搬迁」的第三类目录。

v1 校验五条规则：

R1 `app_lib_top_level`
    `lib/` 顶层只允许 `service/` 容器、`APP_CROSS_CUTTING_ROOTS` 的三个横切根
    （`runtime/`、`design_system/`、l10n 根），以及入口文件 `main*.dart`。

R2 `cross_cutting_target_reverse_import`
    横切面禁止依赖业务对象。目标形态目前几乎不存在（`lib/runtime/`、
    `lib/design_system/` 尚未建立），因此该规则在**目标空间**求值：文件的归属由
    `object_path_map.py` 派生，凡派生归属为横切面的文件，禁止 import 派生归属为
    某个 domain 的文件。这样在物理搬迁（W2/W3）之前就能测出真实的反向依赖量，
    并随搬迁与解耦单调收敛。

R3 `cross_cutting_physical_reverse_import`
    同一方向性约束在**物理空间**的完整表达：物理位于任一 canonical 横切根
    （`lib/runtime/**`、`lib/design_system/**`、l10n 根）的文件，禁止 import 物理位于
    `lib/service/<service>/<context>/<object>/**` 的文件。
    这是搬迁完成后的终态断言；横切面目录建立前它恒为空集。

R4 `cross_object_private_import`
    两个不同业务对象之间的 import/export 只能指向目标对象显式的
    `application/public/**` seam。目标对象的 private application、domain、adapters、
    presentation 都不能被跨对象消费；纯 generated value type 位于共享 contracts
    package，不构成本 App `lib/**` 私有边。该规则是 DEC-019 的绝对零容忍规则，
    不接受 baseline/allowance，也不存在违规吸收入口。

R5 `runtime_di_presentation_purity`
    `runtime/di/**` 只承担 provider、factory、typed `WidgetBuilder` 与 composition
    装配；禁止在组合根定义 Widget 类、业务文案与业务状态。该规则是共享绝对规则，
    不接受 baseline/allowance，也不存在违规吸收入口。

组合根例外（与云侧 `cmd/` 同义，不是逃逸）：`runtime/di/**` 与顶层入口
`main*.dart` 是装配点，其职责就是把各 domain 的实现接线到一起，因此不纳入 R2/R3
的横切面禁令范围。除此之外没有任何豁免。

对象归属一律经 `quwoquan_ops/gate/object_path_map.py` 派生，本门禁不实现第二套
路径反推规则。复用的规则表达：`ObjectRoster`、`CONTRACT_GRAPH_PATH`、
`load_page_claims`、`scan_app`、`APP_ROOT`、`APP_LIB_ROOT`、`APP_SOURCE_SUFFIX`、
`APP_CROSS_CUTTING_ROOTS`。

strict-zero 语义：R1-R5 任一实测条目都直接 BLOCK。迁移期 baseline 已退休；
`quwoquan_ops/policies/gates/app_architecture_baseline.json` 必须不存在，门禁不再提供
写入、吸收或重建 baseline 的入口。

用法
----
    python3 quwoquan_ops/gate/verify_app_architecture.py
    python3 quwoquan_ops/gate/verify_app_architecture.py --domain content
    python3 quwoquan_ops/gate/verify_app_architecture.py --domain content

`--domain <domain>` 供 domain 并行流使用：只检查该 domain 名下的 R2/R3/R4 违规，
R1 与 R5 是共享规则，任何 scope 都全量求值。
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_to_bytes

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm

RULE_ID = "app-architecture/v1"

BASELINE_PATH = (
    ROOT / "quwoquan_ops" / "policies" / "gates" / "app_architecture_baseline.json"
)
RULE_TOP_LEVEL = "app_lib_top_level"
RULE_TARGET_REVERSE_IMPORT = "cross_cutting_target_reverse_import"
RULE_PHYSICAL_REVERSE_IMPORT = "cross_cutting_physical_reverse_import"
RULE_CROSS_OBJECT_PRIVATE_IMPORT = "cross_object_private_import"
RULE_RUNTIME_DI_PRESENTATION_PURITY = "runtime_di_presentation_purity"

#: R1/R5 是共享规则；R2/R3 按被依赖的 domain，R4 按 consumer/source domain
#: 归属到并行流。五条规则全部 strict-zero。
SHARED_RULES = (RULE_TOP_LEVEL, RULE_RUNTIME_DI_PRESENTATION_PURITY)
DOMAIN_RULES = (
    RULE_TARGET_REVERSE_IMPORT,
    RULE_PHYSICAL_REVERSE_IMPORT,
    RULE_CROSS_OBJECT_PRIVATE_IMPORT,
)

#: 顶层唯一允许的文件形态：Flutter 入口。`app_bootstrap.dart` 与 shell 文件属于
#: `runtime/shell/`，不是入口，因此不在此列。定义取自 `object_path_map`，与那里
#: 「入口是终态位置、横切目标路径即自身」的派生同源，不另写一份。
TOP_LEVEL_ENTRY_RE = opm.APP_ENTRY_FILE_RE

#: 组合根：只有它可以同时依赖多个 domain（云侧 `cmd/` 的端侧对等物）。定义取自
#: `object_path_map`，与那里的「组合根不参与对象反推」同源，不另写一份。
COMPOSITION_ROOT_TARGET_PREFIXES = (opm.APP_COMPOSITION_ROOT_TARGET_PREFIX,)
RUNTIME_DI_ROOT = ROOT / opm.APP_LIB_ROOT / "runtime" / "di"
RUNTIME_DI_WIDGET_BASES = frozenset(
    {
        "StatelessWidget",
        "StatefulWidget",
        "ConsumerWidget",
        "ConsumerStatefulWidget",
    }
)
RUNTIME_DI_TEXT_WIDGETS = frozenset({"Text", "RichText", "SelectableText"})
RUNTIME_DI_COPY_ARGUMENTS = frozenset(
    {"label", "message", "placeholder", "subtitle", "title", "tooltip"}
)

PACKAGE_URI_PREFIX = "package:quwoquan_app/"
CLOUD_CONTRACTS_URI_PREFIX = "package:quwoquan_cloud_contracts/"
DART_URI_DIRECTIVE_KINDS = frozenset({"import", "export", "part"})
PERCENT_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")

LIB_PREFIX = f"{opm.APP_LIB_ROOT.as_posix()}/"
APPLICATION_PUBLIC_SEGMENT = "public"


@dataclass(frozen=True)
class DartUriDirective:
    """剥除注释/普通字符串后得到的一条 authored Dart URI directive。"""

    kind: str
    uri: str


@dataclass(frozen=True)
class ResolvedDartUriDirective:
    """Dart directive 及其可选的本 App ``lib/**`` 目标。"""

    kind: str
    uri: str
    target: str | None


def _is_dart_identifier_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "$"}


def _skip_dart_interpolation_expression(source: str, index: int) -> int:
    """Skip a ``${...}`` body, including nested strings/comments/braces."""
    depth = 1
    length = len(source)
    while index < length:
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            comment_start = index
            comment_depth = 1
            index += 2
            while index < length and comment_depth:
                if source.startswith("/*", index):
                    comment_depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    comment_depth -= 1
                    index += 2
                else:
                    index += 1
            if comment_depth:
                raise ValueError(
                    f"unterminated Dart block comment at offset {comment_start}"
                )
            continue
        if source[index] in {"'", '"'}:
            index, _ = _read_dart_string(source, index)
            continue
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError("unterminated Dart string interpolation")


def _read_dart_string(source: str, start: int) -> tuple[int, str]:
    """Read one Dart string without letting interpolation strings desync the lexer."""
    quote = source[start]
    raw = (
        start > 0
        and source[start - 1] in {"r", "R"}
        and (start < 2 or not _is_dart_identifier_char(source[start - 2]))
    )
    delimiter = quote * (3 if source.startswith(quote * 3, start) else 1)
    index = start + len(delimiter)
    length = len(source)
    value: list[str] = []
    while index < length:
        if source.startswith(delimiter, index):
            return index + len(delimiter), "".join(value)
        if not raw and source[index] == "\\":
            if index + 1 >= length:
                break
            value.extend((source[index], source[index + 1]))
            index += 2
            continue
        if not raw and source[index] == "$":
            value.append("$")
            if index + 1 < length and source[index + 1] == "{":
                index = _skip_dart_interpolation_expression(source, index + 2)
                continue
            index += 1
            while index < length and _is_dart_identifier_char(source[index]):
                index += 1
            continue
        value.append(source[index])
        index += 1
    raise ValueError(f"unterminated Dart string at offset {start}")


def _dart_source_tokens(source: str) -> list[tuple[str, str]]:
    """以最小 Dart 词法扫描剥除注释并隔离字符串内容。

    只保留 directive 识别需要的 identifier/string/punctuation token。字符串内容
    作为单个 token 返回，因此其中伪造的 ``import``/``export``/``part`` 永远不会
    被当成代码；嵌套 block comment 与三引号字符串也在词法层处理。
    """
    tokens: list[tuple[str, str]] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            start = index
            depth = 1
            index += 2
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError(f"unterminated Dart block comment at offset {start}")
            continue
        if char in {"'", '"'}:
            index, value = _read_dart_string(source, index)
            tokens.append(("string", value))
            continue
        if char.isalpha() or char in {"_", "$"}:
            end = index + 1
            while end < length and _is_dart_identifier_char(source[end]):
                end += 1
            tokens.append(("identifier", source[index:end]))
            index = end
            continue
        tokens.append(("punctuation", char))
        index += 1
    return tokens


def parse_dart_uri_directives(source: str) -> list[DartUriDirective]:
    """返回 import/export 的全部 conditional URI 与 authored ``part`` URI。

    ``part of`` 声明只标识当前 library owner，不是从本文件发出的依赖边，因此不
    返回。缺分号或缺 URI 的 malformed directive 直接失败，不降级为“无依赖”。
    """
    tokens = _dart_source_tokens(source)
    directives: list[DartUriDirective] = []
    index = 0
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    while index < len(tokens):
        token = tokens[index]
        if token[0] == "punctuation":
            if token[1] == "{":
                brace_depth += 1
            elif token[1] == "}":
                brace_depth = max(0, brace_depth - 1)
            elif token[1] == "(":
                paren_depth += 1
            elif token[1] == ")":
                paren_depth = max(0, paren_depth - 1)
            elif token[1] == "[":
                bracket_depth += 1
            elif token[1] == "]":
                bracket_depth = max(0, bracket_depth - 1)
        if brace_depth or paren_depth or bracket_depth:
            index += 1
            continue
        if token[0] != "identifier" or token[1] not in DART_URI_DIRECTIVE_KINDS:
            index += 1
            continue
        kind = token[1]
        cursor = index + 1
        if kind == "part" and cursor < len(tokens) and tokens[cursor] == (
            "identifier",
            "of",
        ):
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                cursor += 1
            if cursor >= len(tokens):
                raise ValueError("unterminated Dart part-of directive")
            index = cursor + 1
            continue
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor][0] != "string":
            # ``part`` 是 contextual keyword，允许作为普通 identifier（例如
            # closure parameter）。只有 statement boundary 上的 directive 形态才
            # 对缺 URI fail-closed。
            previous = tokens[index - 1] if index else None
            if previous is None or previous == ("punctuation", ";"):
                raise ValueError(f"Dart {kind} directive is missing a URI literal")
            index += 1
            continue
        directive_uris: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "string":
                directive_uris.append(tokens[cursor][1])
            cursor += 1
        if cursor >= len(tokens):
            raise ValueError(f"unterminated Dart {kind} directive")
        if kind == "part" and len(directive_uris) != 1:
            raise ValueError("Dart part directive must contain exactly one URI")
        directives.extend(DartUriDirective(kind, uri) for uri in directive_uris)
        index = cursor + 1
    return directives


# ---------------------------------------------------------------------------
# 真相源载入
# ---------------------------------------------------------------------------


def load_roster() -> opm.ObjectRoster:
    """载入 ContractGraph 对象 roster；domain 集合即顶层白名单的业务部分。"""
    graph = json.loads((ROOT / opm.CONTRACT_GRAPH_PATH).read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)


def l10n_top_level_segment() -> str:
    """l10n 顶层段；派生规则唯一实现在 `object_path_map`，本门禁只转发。"""
    return opm.derive_app_l10n_cross_cutting_root()


def allowed_top_level_directories(roster: opm.ObjectRoster) -> set[str]:
    """`lib/` 顶层允许的目录：service 容器 + 全部 canonical 横切根（含 l10n 根）。

    这里刻意不再把 l10n 根作为白名单的第三类来源单独并入。曾经的两套列表让
    `lib/l10n/**` 同时是「R1 合法顶层」与「派生器眼中待搬去 lib/runtime/l10n 的
    横切件」，其 `status` 停在 `cross_cutting` 而非 `canonical_cross_cutting`，
    于是覆盖率归属把整批 l10n 源码判成无主文件并阻断 App 棘轮。
    """
    return {opm.APP_SERVICE_ROOT_SEGMENT} | set(opm.APP_CROSS_CUTTING_ROOTS)


# ---------------------------------------------------------------------------
# R1：顶层白名单
# ---------------------------------------------------------------------------


def scan_top_level_violations(roster: opm.ObjectRoster) -> list[str]:
    """返回 `lib/` 顶层不在白名单内的条目；目录以 `/` 结尾以示区分。"""
    allowed = allowed_top_level_directories(roster)
    violations: list[str] = []
    for entry in sorted((ROOT / opm.APP_LIB_ROOT).iterdir()):
        if entry.is_dir():
            if entry.name not in allowed:
                violations.append(f"{entry.name}/")
            continue
        if entry.suffix != opm.APP_SOURCE_SUFFIX or not TOP_LEVEL_ENTRY_RE.match(
            entry.name
        ):
            violations.append(entry.name)
    return sorted(violations)


# ---------------------------------------------------------------------------
# 归属派生（全部经 object_path_map，本文件不实现第二套反推规则）
# ---------------------------------------------------------------------------


def _lib_relative(repo_relative_path: str) -> str:
    return repo_relative_path[len(LIB_PREFIX) :]


def derive_target_root(row: dict, roster: opm.ObjectRoster) -> tuple[str, str | None]:
    """把 `object_path_map` 的一行归属折叠成目标树根。

    返回 ``("domain", <domain>)`` / ``("cross_cutting", "runtime"|"design_system")``
    / ``("unresolved", None)``。派生器判不出唯一对象但能判出唯一 domain 时
    （`context_only` / `domain_only` / 同 domain 内歧义），仍按该 domain 计；跨 domain
    的歧义一律 unresolved，绝不代替业务择一。
    """
    if row.get("objectId"):
        return "domain", row["domain"]

    object_ids = row.get("objectIds") or []
    if object_ids:
        domains = {roster.objects[object_id]["domain"] for object_id in object_ids}
        return ("domain", domains.pop()) if len(domains) == 1 else ("unresolved", None)

    context_ids = row.get("contextIds") or []
    if context_ids:
        domains = {context_id.split(".", 1)[0] for context_id in context_ids}
        return ("domain", domains.pop()) if len(domains) == 1 else ("unresolved", None)

    domains_claimed = row.get("domains") or []
    if len(domains_claimed) == 1 and domains_claimed[0] in roster.domains:
        return "domain", domains_claimed[0]

    cross_cutting_root = row.get("crossCuttingRoot")
    if cross_cutting_root:
        return "cross_cutting", cross_cutting_root
    return "unresolved", None


def is_composition_root(library_relative_path: str, target_path: str | None) -> bool:
    """组合根判定：顶层入口，或物理/派生目标落在 `lib/runtime/di/**`。

    物理路径与派生目标都要判：`object_path_map` 的横切目标路径构造只剥离现状
    `core/` 前缀，已经搬到 `lib/runtime/di/` 的文件会被再套一层 `runtime/`，
    单看派生目标会漏判已完成搬迁的组合根。
    """
    if TOP_LEVEL_ENTRY_RE.match(library_relative_path):
        return True
    if library_relative_path.startswith(COMPOSITION_ROOT_TARGET_PREFIXES):
        return True
    if not target_path or not target_path.startswith(LIB_PREFIX):
        return False
    return _lib_relative(target_path).startswith(COMPOSITION_ROOT_TARGET_PREFIXES)


@dataclass(frozen=True)
class AppObjectLibraryIdentity:
    """Canonical App 对象库的精确身份；只接受 object_path_map 目标形态。"""

    object_id: str
    domain: str
    context: str
    object_name: str
    layer: str


class AppSourceIndex:
    """端侧 `lib/**` 生产文件的归属索引，唯一来源是 `object_path_map.scan_app`。"""

    def __init__(self, roster: opm.ObjectRoster) -> None:
        page_claims, _ = opm.load_page_claims()
        rows, _ = opm.scan_app(roster, page_claims)
        self.roster = roster
        self.target_root: dict[str, tuple[str, str | None]] = {}
        self.object_identity: dict[str, AppObjectLibraryIdentity] = {}
        self.composition_root: set[str] = set()
        self._directives_cache: dict[str, list[ResolvedDartUriDirective]] = {}
        for row in rows:
            if row["role"] != "production":
                continue
            library_relative = _lib_relative(row["path"])
            self.target_root[library_relative] = derive_target_root(row, roster)
            shape = opm.derive_app_target_shape_identity(
                tuple(library_relative.split("/")), roster
            )
            if shape is not None:
                domain, context, object_name, layer = shape
                record = roster.by_key[(domain, context, object_name)]
                self.object_identity[library_relative] = AppObjectLibraryIdentity(
                    object_id=record["objectId"],
                    domain=domain,
                    context=context,
                    object_name=object_name,
                    layer=layer,
                )
            if is_composition_root(library_relative, row.get("targetPath")):
                self.composition_root.add(library_relative)

    def physical_root(self, library_relative_path: str) -> tuple[str, str | None]:
        """物理树根：横切根或 canonical service 对象树。"""
        parts = tuple(library_relative_path.split("/"))
        head = parts[0]
        if head in opm.APP_CROSS_CUTTING_ROOTS:
            return "cross_cutting", head
        identity = opm.derive_app_target_shape_identity(parts, self.roster)
        if identity is not None:
            return "domain", identity[0]
        return "unresolved", None

    def directives(
        self, library_relative_path: str
    ) -> list[ResolvedDartUriDirective]:
        """词法解析所有 import/export/part URI，并解析本 App 目标。"""
        cached = self._directives_cache.get(library_relative_path)
        if cached is not None:
            return cached
        text = (ROOT / opm.APP_LIB_ROOT / library_relative_path).read_text(
            encoding="utf-8", errors="replace"
        )
        resolved: list[ResolvedDartUriDirective] = []
        try:
            authored = parse_dart_uri_directives(text)
            for directive in authored:
                target = _resolve_import_uri(library_relative_path, directive.uri)
                resolved.append(
                    ResolvedDartUriDirective(
                        kind=directive.kind,
                        uri=directive.uri,
                        target=(
                            target
                            if target is not None and target in self.target_root
                            else None
                        ),
                    )
                )
        except ValueError as error:
            raise ValueError(f"{library_relative_path}: {error}") from error
        self._directives_cache[library_relative_path] = resolved
        return resolved

    def imports(self, library_relative_path: str) -> list[str]:
        """返回 import/export/part 的全部已解析本包 ``lib/**`` 目标。"""
        return [
            directive.target
            for directive in self.directives(library_relative_path)
            if directive.target is not None
        ]


def _percent_decode_uri(uri: str) -> str:
    """按 Dart URI 路径语义单次解码 percent escape，非法 UTF-8 直接阻断。"""
    cursor = 0
    while cursor < len(uri):
        if uri[cursor] != "%":
            cursor += 1
            continue
        if not PERCENT_ESCAPE_RE.match(uri, cursor):
            raise ValueError(f"Dart dependency URI 含非法 percent escape: {uri!r}")
        cursor += 3
    try:
        return unquote_to_bytes(uri).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"Dart dependency URI percent escape 不是 UTF-8: {uri!r}"
        ) from error


def _resolve_import_uri(library_relative_path: str, uri: str) -> str | None:
    uri = _percent_decode_uri(uri)
    if not uri or "\\" in uri or "$" in uri or "\x00" in uri:
        raise ValueError(f"Dart dependency URI 必须是静态 POSIX 路径: {uri!r}")
    if uri.startswith(PACKAGE_URI_PREFIX):
        relative = posixpath.normpath(uri[len(PACKAGE_URI_PREFIX) :])
        if relative in {"", ".", ".."} or relative.startswith(("/", "../")):
            raise ValueError(f"package:quwoquan_app URI 越出 lib/: {uri!r}")
        return relative
    if ":" in uri.split("/", 1)[0]:
        # dart:*、其他 package:* 与 asset scheme 都不构成本包内依赖边。
        return None
    if uri.startswith("/"):
        raise ValueError(f"相对 Dart dependency URI 不得是绝对路径: {uri!r}")
    relative = posixpath.normpath(
        posixpath.join(posixpath.dirname(library_relative_path), uri)
    )
    if relative in {"", ".", ".."} or relative.startswith(("/", "../")):
        raise ValueError(
            f"Dart dependency URI 从 {library_relative_path!r} 越出 lib/: {uri!r}"
        )
    return relative


# ---------------------------------------------------------------------------
# R2 / R3：横切面反向 import 禁令
# ---------------------------------------------------------------------------


def _edge(source: str, target: str) -> str:
    return f"{source} -> {target}"


def scan_reverse_import_violations(
    index: AppSourceIndex,
    *,
    physical: bool,
) -> dict[str, list[str]]:
    """按被依赖 domain 聚合横切面 → 业务对象的反向依赖边。

    ``physical=False`` 在目标空间求值（R2），``physical=True`` 在物理空间求值（R3）。
    """
    def classify(library_relative_path: str) -> tuple[str, str | None]:
        if physical:
            return index.physical_root(library_relative_path)
        return index.target_root.get(library_relative_path, ("unresolved", None))

    violations: dict[str, list[str]] = {}
    for library_relative in sorted(index.target_root):
        kind, _ = classify(library_relative)
        if kind != "cross_cutting":
            continue
        if library_relative in index.composition_root:
            continue
        for imported in index.imports(library_relative):
            imported_kind, imported_domain = classify(imported)
            if imported_kind != "domain":
                continue
            violations.setdefault(imported_domain, []).append(
                _edge(library_relative, imported)
            )
    return {domain: sorted(edges) for domain, edges in sorted(violations.items())}


# ---------------------------------------------------------------------------
# R4：跨对象只能 import 目标对象显式 public seam
# ---------------------------------------------------------------------------


def is_cross_object_public_seam(
    library_relative_path: str,
    identity: AppObjectLibraryIdentity,
) -> bool:
    """仅承认 ``<object>/application/public/**``，不承认同名文件或 barrel。"""
    parts = library_relative_path.split("/")
    return (
        identity.layer == "application"
        and len(parts) > opm.APP_TARGET_SHAPE_SEGMENTS + 1
        and parts[opm.APP_TARGET_SHAPE_SEGMENTS] == APPLICATION_PUBLIC_SEGMENT
    )


def _cross_object_edge(kind: str, source: str, target: str) -> str:
    return f"{kind}: {source} -> {target}"


def _is_public_seam_external_value_dependency(uri: str) -> bool:
    """public seam 外部依赖只认 Dart SDK 与唯一 generated contracts 包。"""
    return uri.startswith(("dart:", CLOUD_CONTRACTS_URI_PREFIX))


def scan_cross_object_private_import_violations(
    index: AppSourceIndex,
) -> dict[str, list[str]]:
    """按 consumer/source domain 聚合绕过 public seam 的 authored directives。

    同对象内部依赖不由本规则重复约束；runtime/design_system/l10n 与尚未完成 R1
    迁移的旧技术根没有 canonical 对象身份，也不在这里被误判。它们各自由 R1-R3
    及对象路径门禁负责。目标 identity 不可派生时同样不猜 legacy/generated owner。
    共享 contracts package 不属于本包 ``lib/**``，自然不形成私有对象边。

    ``application/public/**`` 是显式 seam 文件，不是 export barrel 根；public 文件的
    authored export 无论目标归属都阻断。public 文件的 same-object import 仍允许，
    以便 seam 声明使用本对象 domain 实现类型。
    """
    violations: dict[str, set[str]] = {}
    for library_relative, source_identity in sorted(index.object_identity.items()):
        source_is_public = is_cross_object_public_seam(
            library_relative, source_identity
        )
        for directive in index.directives(library_relative):
            if source_is_public:
                # public seam 是显式文件而非 barrel/part library；其外部类型
                # 依赖只能来自 Dart SDK 或唯一 generated contracts package。
                if directive.kind in {"export", "part"}:
                    violations.setdefault(source_identity.domain, set()).add(
                        _cross_object_edge(
                            directive.kind,
                            library_relative,
                            directive.target or directive.uri,
                        )
                    )
                    continue
                if directive.target is None:
                    if not _is_public_seam_external_value_dependency(directive.uri):
                        violations.setdefault(source_identity.domain, set()).add(
                            _cross_object_edge(
                                directive.kind, library_relative, directive.uri
                            )
                        )
                    continue
                target_identity = index.object_identity.get(directive.target)
                if target_identity is None:
                    # public seam 的依赖闭集比一般 R4 更严格：本包内无法归属到
                    # canonical object 的 legacy/local-generated/cross-cutting 目标
                    # 一律不能作为公开接口类型来源。纯 generated value type 必须
                    # 经唯一 quwoquan_cloud_contracts package 进入。
                    violations.setdefault(source_identity.domain, set()).add(
                        _cross_object_edge(
                            directive.kind, library_relative, directive.target
                        )
                    )
                    continue
                if target_identity.object_id == source_identity.object_id:
                    if target_identity.layer == "domain" or is_cross_object_public_seam(
                        directive.target, target_identity
                    ):
                        continue
                    violations.setdefault(source_identity.domain, set()).add(
                        _cross_object_edge(
                            directive.kind, library_relative, directive.target
                        )
                    )
                    continue
                if is_cross_object_public_seam(directive.target, target_identity):
                    continue
                violations.setdefault(source_identity.domain, set()).add(
                    _cross_object_edge(
                        directive.kind, library_relative, directive.target
                    )
                )
                continue
            if directive.target is None:
                continue
            target_identity = index.object_identity.get(directive.target)
            if target_identity is None:
                continue
            if target_identity.object_id == source_identity.object_id:
                continue
            if is_cross_object_public_seam(directive.target, target_identity):
                continue
            violations.setdefault(source_identity.domain, set()).add(
                _cross_object_edge(
                    directive.kind, library_relative, directive.target
                )
            )
    return {
        domain: sorted(edges) for domain, edges in sorted(violations.items())
    }


# ---------------------------------------------------------------------------
# R5：runtime/di 只做装配，不定义 presentation
# ---------------------------------------------------------------------------


def _dart_type_declarations(
    tokens: list[tuple[str, str]],
) -> list[tuple[str, str, str | None]]:
    """返回 ``(kind, name, extends)``，忽略注释与字符串里的伪声明。"""
    declarations: list[tuple[str, str, str | None]] = []
    for index, token in enumerate(tokens):
        if token[0] != "identifier" or token[1] not in {"class", "enum", "typedef"}:
            continue
        if index + 1 >= len(tokens) or tokens[index + 1][0] != "identifier":
            continue
        kind = token[1]
        name = tokens[index + 1][1]
        base: str | None = None
        cursor = index + 2
        while cursor < len(tokens):
            current = tokens[cursor]
            if current in {("punctuation", "{"), ("punctuation", ";")}:
                break
            if current == ("identifier", "extends"):
                if cursor + 1 < len(tokens) and tokens[cursor + 1][0] == "identifier":
                    base = tokens[cursor + 1][1]
                break
            cursor += 1
        declarations.append((kind, name, base))
    return declarations


def scan_runtime_di_presentation_purity_violations(
    runtime_di_root: Path = RUNTIME_DI_ROOT,
) -> list[str]:
    """找出组合根内自定义 Widget、业务文案与业务状态。

    Provider/Notifier 使用既有状态类型、factory、composition 和 typed
    ``WidgetBuilder`` 都不触发。只有在 ``runtime/di`` **定义** presentation
    类型/状态，或直接作者化用户可见文案时才阻断。
    """
    if not runtime_di_root.is_dir():
        return []
    findings: set[str] = set()
    for path in sorted(runtime_di_root.rglob("*.dart")):
        source = path.read_text(encoding="utf-8", errors="replace")
        tokens = _dart_source_tokens(source)
        relative = (Path("runtime/di") / path.relative_to(runtime_di_root)).as_posix()
        widget_classes: set[str] = set()
        business_states: set[str] = set()
        copy_kinds: set[str] = set()

        for kind, name, base in _dart_type_declarations(tokens):
            if base in RUNTIME_DI_WIDGET_BASES:
                widget_classes.add(f"{name} extends {base}")
            if name.endswith("State"):
                business_states.add(f"{kind} {name}")

        for index, token in enumerate(tokens):
            if token[0] != "identifier":
                continue
            name = token[1]
            if (
                name in RUNTIME_DI_TEXT_WIDGETS
                and index + 1 < len(tokens)
                and tokens[index + 1] == ("punctuation", "(")
            ):
                copy_kinds.add("text_widget")
            if (
                name.endswith(("Copy", "Strings", "Text"))
                and index + 2 < len(tokens)
                and tokens[index + 1] == ("punctuation", ".")
                and tokens[index + 2][0] == "identifier"
            ):
                copy_kinds.add("text_catalog")
            if (
                name in RUNTIME_DI_COPY_ARGUMENTS
                and index + 2 < len(tokens)
                and tokens[index + 1] == ("punctuation", ":")
            ):
                value_index = index + 2
                if (
                    tokens[value_index] in {
                        ("identifier", "r"),
                        ("identifier", "R"),
                    }
                    and value_index + 1 < len(tokens)
                ):
                    value_index += 1
                if tokens[value_index][0] == "string":
                    copy_kinds.add("literal")
        if widget_classes:
            findings.add(
                f"{relative}: widget_class [{', '.join(sorted(widget_classes))}]"
            )
        if business_states:
            findings.add(
                f"{relative}: business_state [{', '.join(sorted(business_states))}]"
            )
        if copy_kinds:
            findings.add(
                f"{relative}: business_copy [{', '.join(sorted(copy_kinds))}]"
            )
    return sorted(findings)


# ---------------------------------------------------------------------------
# 违规汇总与基线比对
# ---------------------------------------------------------------------------


def evaluate(roster: opm.ObjectRoster) -> dict:
    """求值五条规则，返回 ``{"shared": {...}, "domains": {...}}``。"""
    index = AppSourceIndex(roster)
    target_reverse = scan_reverse_import_violations(index, physical=False)
    physical_reverse = scan_reverse_import_violations(index, physical=True)
    cross_object_private = scan_cross_object_private_import_violations(index)

    domains: dict[str, dict[str, list[str]]] = {}
    for domain in sorted(
        set(target_reverse) | set(physical_reverse) | set(cross_object_private)
    ):
        domains[domain] = {
            RULE_TARGET_REVERSE_IMPORT: target_reverse.get(domain, []),
            RULE_PHYSICAL_REVERSE_IMPORT: physical_reverse.get(domain, []),
            RULE_CROSS_OBJECT_PRIVATE_IMPORT: cross_object_private.get(domain, []),
        }
    return {
        "shared": {
            RULE_TOP_LEVEL: scan_top_level_violations(roster),
            RULE_RUNTIME_DI_PRESENTATION_PURITY: (
                scan_runtime_di_presentation_purity_violations()
            ),
        },
        "domains": domains,
    }


def verify_retired_baseline_absent() -> None:
    """迁移期 baseline 已退休；重新出现即是第二条准入真相源。"""
    if BASELINE_PATH.exists():
        raise ValueError(
            f"{BASELINE_PATH}: retired baseline must remain absent; "
            "R1-R5 are strict-zero"
        )


def _normalized(document: dict) -> dict:
    """规范化违规文档：条目去重排序，空 domain 分区剔除。

    去重只合并完全相同的 authored edge；R4 条目含 directive kind，因此
    同一 source/target 的 import、export、part 仍是三条不同证据。
    """
    shared = {
        rule: sorted(set(document.get("shared", {}).get(rule, []) or []))
        for rule in SHARED_RULES
    }
    domains: dict[str, dict[str, list[str]]] = {}
    for domain, section in sorted((document.get("domains") or {}).items()):
        entries = {
            rule: sorted(set(section.get(rule, []) or [])) for rule in DOMAIN_RULES
        }
        if any(entries.values()):
            domains[domain] = entries
    return {"shared": shared, "domains": domains}


def _rule_entries(document: dict, domain: str | None, rule: str) -> set[str]:
    if rule in SHARED_RULES:
        return set(document.get("shared", {}).get(rule, []) or [])
    section = (document.get("domains") or {}).get(domain) or {}
    return set(section.get(rule, []) or [])


def scoped_domains(current: dict, domain: str | None) -> list[str]:
    if domain is not None:
        return [domain]
    return sorted(current.get("domains") or {})


def violation_entries(current: dict, domain: str | None) -> list[str]:
    """返回 scope 内全部 strict-zero 违规；不存在 baseline 差分。"""
    entries = [
        f"{rule}: {entry}"
        for rule in SHARED_RULES
        for entry in sorted(_rule_entries(current, None, rule))
    ]
    for scoped_domain in scoped_domains(current, domain):
        for rule in DOMAIN_RULES:
            entries += [
                f"{rule}[{scoped_domain}]: {entry}"
                for entry in sorted(_rule_entries(current, scoped_domain, rule))
            ]
    return entries


def summarize(current: dict, domain: str | None) -> dict:
    """派生本次求值的违规计数摘要。"""
    domains = scoped_domains(current, domain)
    counts = {rule: len(_rule_entries(current, None, rule)) for rule in SHARED_RULES}
    for rule in DOMAIN_RULES:
        counts[rule] = sum(
            len(_rule_entries(current, scoped_domain, rule))
            for scoped_domain in domains
        )
    by_domain = {
        scoped_domain: {
            rule: len(_rule_entries(current, scoped_domain, rule))
            for rule in DOMAIN_RULES
        }
        for scoped_domain in domains
        if any(_rule_entries(current, scoped_domain, rule) for rule in DOMAIN_RULES)
    }
    return {
        "ruleId": RULE_ID,
        "scope": domain or "all",
        "violations": counts,
        "violationsByDomain": by_domain,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "端侧对象化架构门禁 v1（顶层白名单 + 横切面反向 import + "
            "跨对象 public seam + runtime/di presentation purity）"
        )
    )
    parser.add_argument(
        "--domain",
        default=None,
        help=(
            "只比对该 domain 名下的 R2/R3/R4 违规；"
            "R1/R5 共享规则始终全量求值"
        ),
    )
    arguments = parser.parse_args(argv)

    roster = load_roster()
    if arguments.domain is not None and arguments.domain not in roster.domains:
        print(
            f"verify_app_architecture: BLOCK: 未知 domain {arguments.domain!r}，"
            f"ContractGraph roster 只有 {sorted(roster.domains)}",
            file=sys.stderr,
        )
        return 2

    try:
        current = _normalized(evaluate(roster))
    except (OSError, ValueError) as error:
        print(
            f"verify_app_architecture: FAIL Dart dependency scan: {error}",
            file=sys.stderr,
        )
        return 1

    try:
        verify_retired_baseline_absent()
    except ValueError as error:
        print(f"verify_app_architecture: BLOCK: {error}", file=sys.stderr)
        return 1

    violations = violation_entries(current, arguments.domain)
    if violations:
        print("verify_app_architecture: BLOCK: strict-zero violation", file=sys.stderr)
        for entry in violations:
            print(f"  violation: {entry}", file=sys.stderr)
        print(
            "  lib/ 顶层只允许 service/、runtime/、design_system/、l10n/ 与 "
            "main*.dart；runtime/** 与 design_system/** 不得依赖任何 "
            "lib/service/<service>/<context>/<object>/**"
            "（组合根 runtime/di/** 与入口除外）。"
            "不同业务对象之间只能 import 目标对象 application/public/**；"
            "runtime/di/** 只能定义 provider/factory/typed WidgetBuilder/composition，"
            "不得定义 Widget、业务文案或业务状态。R1-R5 全部 strict-zero，"
            "不接受 baseline/allowance。",
            file=sys.stderr,
        )
        return 1

    summary = summarize(current, arguments.domain)
    print(f"verify_app_architecture: OK (scope={summary['scope']})")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
