"""
与 page_object_contract / verify_page_abc_governance 共用的磁盘页面路径枚举。

修改扫描规则时须只改本模块，避免两套脚本漂移。
"""

from __future__ import annotations

from pathlib import Path


def _add_page_files(
    out: set[str],
    *,
    app: Path,
    root: Path,
) -> None:
    if not root.is_dir():
        return
    for path in root.rglob("*_page.dart"):
        relative = path.relative_to(app).as_posix()
        out.add(relative)


def _add_suffix_files(
    out: set[str],
    *,
    app: Path,
    root: Path,
    suffix: str,
) -> None:
    if not root.is_dir():
        return
    for path in root.rglob(f"*{suffix}"):
        relative = path.relative_to(app).as_posix()
        out.add(relative)


def matrix_disk_scan_paths(repo_root: Path) -> frozenset[str]:
    """返回 quwoquan_app 相对路径集合；目录扫描就是页面集合真相。

    service-owned canonical 对象页面只从
    ``service/<service>/<domain>/<object>/presentation`` 扫描，避免把
    domain/transport 中名称带 ``page`` 的值对象误当页面。迁移前的
    ``ui``/``components``/``app/shell`` 继续按原规则扫描，确保残留页面仍必须由
    page_object_contract 唯一认领。``runtime/shell`` 承载不依赖业务对象的全局壳页面；
    ``runtime/di/shell`` 承载需要组装业务对象的 App composition root。两者递归扫描
    具名 ``*_page.dart`` / ``*_screen.dart``，composition root 还扫描 helper 文件。
    设计系统只扫描显式 ``*_page.dart``。
    """
    app = repo_root / "quwoquan_app"
    lib = app / "lib"
    out: set[str] = set()
    if not lib.is_dir():
        return frozenset()
    _add_page_files(out, app=app, root=lib / "design_system")

    # Canonical service-owned object tree. Requiring the fifth segment below
    # lib/service to be presentation keeps the physical owner unique and
    # rejects service/domain/context-only nesting.
    service_root = lib / "service"
    if service_root.is_dir():
        for service in service_root.iterdir():
            if not service.is_dir():
                continue
            for domain in service.iterdir():
                if not domain.is_dir():
                    continue
                for object_root in domain.iterdir():
                    _add_page_files(
                        out,
                        app=app,
                        root=object_root / "presentation",
                    )

    # Preserve canonical object roots that do not live below lib/service.
    for domain in lib.iterdir():
        if not domain.is_dir() or domain.name in {
            "service",
            "runtime",
            "design_system",
            "l10n",
            "ui",
            "components",
        }:
            continue
        for context in domain.iterdir():
            if not context.is_dir():
                continue
            for object_root in context.iterdir():
                presentation = object_root / "presentation"
                _add_page_files(out, app=app, root=presentation)

    # Migration compatibility is still a positive scan: any page left in an
    # old root must remain uniquely registered until it is physically moved.
    _add_page_files(out, app=app, root=lib / "ui")
    welcome = lib / "ui" / "welcome" / "pages" / "welcome_screen.dart"
    if welcome.is_file():
        out.add(welcome.relative_to(app).as_posix())
    _add_page_files(out, app=app, root=lib / "components")
    legacy_shell = lib / "app" / "shell"
    if legacy_shell.is_dir():
        for path in legacy_shell.glob("*.dart"):
            out.add(path.relative_to(app).as_posix())

    shell = lib / "runtime/shell"
    if shell.is_dir():
        _add_page_files(out, app=app, root=shell)
        _add_suffix_files(
            out,
            app=app,
            root=shell,
            suffix="_screen.dart",
        )
        for path in shell.glob("*.dart"):
            if path.name.endswith("_providers.dart"):
                continue
            out.add(path.relative_to(app).as_posix())

    composition_shell = lib / "runtime/di/shell"
    if composition_shell.is_dir():
        _add_page_files(out, app=app, root=composition_shell)
        _add_suffix_files(
            out,
            app=app,
            root=composition_shell,
            suffix="_screen.dart",
        )
        for path in composition_shell.glob("*.dart"):
            if path.name.endswith("_providers.dart"):
                continue
            out.add(path.relative_to(app).as_posix())

    composition_presentation = lib / "runtime/di/presentation"
    if composition_presentation.is_dir():
        _add_page_files(out, app=app, root=composition_presentation)
    return frozenset(out)
