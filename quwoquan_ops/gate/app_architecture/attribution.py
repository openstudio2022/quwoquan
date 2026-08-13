"""真相源载入、R1 顶层白名单与对象归属派生（全部经 object_path_map）。"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from urllib.parse import unquote_to_bytes

from quwoquan_ops.gate import object_path_map as opm

from .constants import (
    COMPOSITION_ROOT_TARGET_PREFIXES,
    LIB_PREFIX,
    PACKAGE_URI_PREFIX,
    PERCENT_ESCAPE_RE,
    ROOT,
    TOP_LEVEL_ENTRY_RE,
)
from .dart_lexer import parse_dart_uri_directives


@dataclass(frozen=True)
class ResolvedDartUriDirective:
    """Dart directive 及其可选的本 App ``lib/**`` 目标。"""

    kind: str
    uri: str
    target: str | None


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
# 归属派生（全部经 object_path_map，本包不实现第二套反推规则）
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
