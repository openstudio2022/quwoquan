"""
与 verify_page_matrix_scan_complete / verify_page_abc_governance 共用的磁盘页面路径枚举。

修改扫描规则时须只改本模块，避免两套脚本漂移。
"""

from __future__ import annotations

from pathlib import Path

EXCLUDE_REL = frozenset({"lib/ui/chat/pages/chat_display_fallbacks.dart"})


def matrix_disk_scan_paths(repo_root: Path) -> frozenset[str]:
    """返回 quwoquan_app 相对路径集合（与 page-horizontal-quality 矩阵扫描基线一致）。"""
    app = repo_root / "quwoquan_app"
    lib = app / "lib"
    out: set[str] = set()
    if not lib.is_dir():
        return frozenset()
    ui = lib / "ui"
    if ui.is_dir():
        for p in ui.rglob("*_page.dart"):
            rel = p.relative_to(app).as_posix()
            if rel in EXCLUDE_REL:
                continue
            out.add(rel)
        welcome = ui / "welcome/pages/welcome_screen.dart"
        if welcome.is_file():
            out.add(welcome.relative_to(app).as_posix())
    comp = lib / "components"
    if comp.is_dir():
        for p in comp.rglob("*_page.dart"):
            out.add(p.relative_to(app).as_posix())
    shell = lib / "app/shell"
    if shell.is_dir():
        for p in shell.glob("*.dart"):
            out.add(p.relative_to(app).as_posix())
    return frozenset(out)
