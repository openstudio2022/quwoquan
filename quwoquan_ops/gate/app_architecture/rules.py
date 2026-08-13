"""R2/R3 横切面反向 import、R4 跨对象 public seam 与 R5 runtime/di purity 扫描。"""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.gate import object_path_map as opm

from .attribution import AppObjectLibraryIdentity, AppSourceIndex
from .constants import (
    APPLICATION_PUBLIC_SEGMENT,
    CLOUD_CONTRACTS_URI_PREFIX,
    RUNTIME_DI_COPY_ARGUMENTS,
    RUNTIME_DI_ROOT,
    RUNTIME_DI_TEXT_WIDGETS,
    RUNTIME_DI_WIDGET_BASES,
)
from .dart_lexer import _dart_source_tokens, _dart_type_declarations


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
