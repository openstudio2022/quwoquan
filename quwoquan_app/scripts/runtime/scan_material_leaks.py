#!/usr/bin/env python3
"""
Inventory Material API surface usage under quwoquan_app/lib/ui and lib/components.

Outputs (repo root):
  - specs/inventories/material_leak_lib_ui_components.yaml
  - specs/inventories/material_leak_lib_ui_components.md

This is documentation / debt tracking only — not a CI gate.
Re-run: python3 scripts/scan_material_leaks.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
OUT_YAML = ROOT / "specs" / "inventories" / "material_leak_lib_ui_components.yaml"
OUT_MD = ROOT / "specs" / "inventories" / "material_leak_lib_ui_components.md"

SCOPES: tuple[tuple[str, Path], ...] = (
    ("ui", APP_LIB / "ui"),
    ("components", APP_LIB / "components"),
)

_MATERIAL_IMPORT = re.compile(
    r"""^import\s+['\"]package:flutter/material\.dart['\"]\s*(show\s+[^;]+)?;""",
    re.MULTILINE,
)
_CUPERTINO_IMPORT = re.compile(
    r"""^import\s+['\"]package:flutter/cupertino\.dart['\"]\s*;""",
    re.MULTILINE,
)

# Heuristic tokens: counts are non-authoritative (comments/strings may match).
SIGNALS: tuple[tuple[str, str], ...] = (
    ("scaffold", r"\bScaffold\s*\("),
    ("app_bar", r"\bAppBar\s*\("),
    ("sliver_app_bar", r"\bSliverAppBar\s*\("),
    ("snack_bar", r"\bSnackBar\b"),
    ("floating_action_button", r"\bFloatingActionButton\b"),
    ("material", r"\bMaterial\s*\("),
    ("ink_well", r"\bInkWell\b|\bInkResponse\b"),
    (
        "material_buttons",
        r"\b(ElevatedButton|TextButton|OutlinedButton|FilledButton|IconButton)\s*\(",
    ),
    ("list_tile", r"\bListTile\s*\("),
    ("drawer", r"\bDrawer\s*\("),
    ("modal_bottom_sheet", r"\bshowModalBottomSheet\s*\("),
    ("bottom_sheet_theme", r"\bshowBottomSheet\s*\("),
    ("bottom_nav_bar", r"\bBottomNavigationBar\b"),
    ("navigation_rail", r"\bNavigationRail\b"),
    ("m3_navigation_bar", r"\bNavigationBar\s*\("),
    ("tab_bar", r"\bTabBar\s*\("),
    ("tab_controller", r"\bTabController\b"),
    ("dropdown", r"\bDropdownButton\b"),
    ("popup_menu", r"\bPopupMenuButton\b"),
    ("search_anchor", r"\bSearchAnchor\b|\bSearchBar\b"),
    ("chip", r"\b(FilterChip|ActionChip|ChoiceChip|InputChip)\s*\("),
    ("raw_chip", r"\bChip\s*\("),
    ("card", r"\bCard\s*\("),
    ("dialog", r"\b(AlertDialog|SimpleDialog)\s*\("),
    ("theme_of", r"\bTheme\.of\s*\("),
    ("material_page_route", r"\bMaterialPageRoute\b"),
    ("colors_dot", r"\bColors\."),
    ("divider", r"\bDivider\s*\("),
    ("vertical_divider", r"\bVerticalDivider\s*\("),
    ("refresh_indicator", r"\bRefreshIndicator\s*\("),
    ("reorderable_list", r"\bReorderableListView\b"),
    ("data_table", r"\b(DataTable|PaginatedDataTable)\b"),
    ("tooltip", r"\bTooltip\s*\("),
    ("menu_anchor", r"\bMenuAnchor\b"),
    ("switch_material", r"\bSwitch\s*\("),
    ("checkbox", r"\bCheckbox\s*\("),
    ("radio", r"\bRadio\s*\("),
    ("slider", r"\bSlider\s*\("),
    ("range_slider", r"\bRangeSlider\s*\("),
)


def _dart_files_under(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.dart"))


def _material_import_kind(text: str) -> tuple[str, str | None]:
    m = _MATERIAL_IMPORT.search(text)
    if not m:
        return "none", None
    show_clause = m.group(1)
    if show_clause:
        return "show", show_clause.strip()
    return "full", None


def _has_cupertino(text: str) -> bool:
    return _CUPERTINO_IMPORT.search(text) is not None


def _signal_counts(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, pattern in SIGNALS:
        rx = re.compile(pattern)
        n = len(rx.findall(text))
        if n:
            out[name] = n
    return out


def _yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(c in s for c in '":#\n\\'):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def main() -> int:
    if not APP_LIB.is_dir():
        print(f"[scan_material_leaks] FAIL: missing {APP_LIB}", file=sys.stderr)
        return 2

    rows: list[dict[str, object]] = []
    global_signals: dict[str, int] = defaultdict(int)
    dart_total = 0

    for zone, base in SCOPES:
        for path in _dart_files_under(base):
            dart_total += 1
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            kind, show_detail = _material_import_kind(text)
            signals = _signal_counts(text)
            for k, v in signals.items():
                global_signals[k] += v
            rows.append(
                {
                    "path": rel,
                    "zone": zone,
                    "material_import": kind,
                    "material_show": show_detail,
                    "imports_cupertino": _has_cupertino(text),
                    "signals": signals,
                }
            )

    rows.sort(key=lambda r: r["path"] if isinstance(r["path"], str) else "")

    material_any = sum(
        1 for r in rows if r["material_import"] != "none"  # type: ignore[comparison-overlap]
    )
    material_full = sum(1 for r in rows if r["material_import"] == "full")
    material_show = sum(1 for r in rows if r["material_import"] == "show")
    no_material = dart_total - material_any

    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    yl: list[str] = [
        "# Auto-generated by scripts/scan_material_leaks.py — do not hand-edit.",
        f"generated_at: {_yaml_escape(now)}",
        "policy_note: Heuristic regex counts may include comments/strings; use as triage, not proof.",
        "scopes:",
        "  - quwoquan_app/lib/ui",
        "  - quwoquan_app/lib/components",
        "summary:",
        f"  dart_files: {dart_total}",
        f"  imports_material_any: {material_any}",
        f"  imports_material_full: {material_full}",
        f"  imports_material_show_only: {material_show}",
        f"  no_material_import: {no_material}",
        "global_signal_hits:",
    ]
    for name in sorted(global_signals.keys()):
        yl.append(f"  {name}: {global_signals[name]}")
    yl.append("files:")
    for r in rows:
        yl.append(f"  - path: {_yaml_escape(str(r['path']))}")
        yl.append(f"    zone: {r['zone']}")
        yl.append(f"    material_import: {r['material_import']}")
        if r["material_show"]:
            yl.append(f"    material_show: {_yaml_escape(str(r['material_show']))}")
        yl.append(f"    imports_cupertino: {str(bool(r['imports_cupertino'])).lower()}")
        sig = r["signals"] if isinstance(r["signals"], dict) else {}
        if sig:
            yl.append("    signals:")
            for sk in sorted(sig.keys()):
                yl.append(f"      {sk}: {sig[sk]}")
    OUT_YAML.write_text("\n".join(yl) + "\n", encoding="utf-8")

    # Markdown (human-readable)
    md: list[str] = [
        "# lib/ui + lib/components Material 泄露清单",
        "",
        f"- **生成时间（UTC）**：{now}",
        "- **范围**：`quwoquan_app/lib/ui`、`quwoquan_app/lib/components` 下全部 `.dart`",
        "- **复跑**：`python3 scripts/scan_material_leaks.py`",
        "- **说明**：`material_import` 表示是否 `import 'package:flutter/material.dart'`；`signals` 为启发式正则命中次数（注释/字符串可能误报），用于排期与分桶，不作严格证明。",
        "",
        "## 摘要",
        "",
        f"| 指标 | 数量 |",
        f"| --- | ---: |",
        f"| Dart 文件总数 | {dart_total} |",
        f"| 任意形式依赖 material.dart（含 `show`） | {material_any} |",
        f"| 整库 import material（非 show） | {material_full} |",
        f"| 仅 `show …` 从 material 引用符号 | {material_show} |",
        f"| 未 import material.dart | {no_material} |",
        "",
        "## 全局 signal 命中（跨文件合计）",
        "",
        "| signal | hits |",
        "| --- | ---: |",
    ]
    for name in sorted(global_signals.keys()):
        md.append(f"| `{name}` | {global_signals[name]} |")
    md.extend(
        [
            "",
            "## 按文件（有 material import 或存在 signal 命中）",
            "",
            "| path | zone | material | cupertino | signals（摘要） |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for r in rows:
        mi = r["material_import"]
        if mi == "none" and not r["signals"]:
            continue
        sig = r["signals"] if isinstance(r["signals"], dict) else {}
        top = ", ".join(f"`{k}`×{sig[k]}" for k in sorted(sig.keys())[:8])
        if len(sig) > 8:
            top += ", …"
        mat_cell = str(mi)
        if r["material_show"]:
            mat_cell += f" ({r['material_show']})"
        md.append(
            f"| `{r['path']}` | {r['zone']} | {mat_cell} | "
            f"{'yes' if r['imports_cupertino'] else 'no'} | {top or '—'} |"
        )

    md.extend(
        [
            "",
            "## 未 import material 且无表中 signal 命中的文件",
            "",
            "以下文件在本脚本的 signal 规则下未记到典型 Material 控件模式；仍可能通过其他库间接依赖 Material（例如 `flutter/widgets.dart` 不包含 Material 组件，但父级 `Material` 祖先由路由/壳注入）。",
            "",
        ]
    )
    for r in rows:
        if r["material_import"] != "none" or r["signals"]:
            continue
        md.append(f"- `{r['path']}`")

    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"[scan_material_leaks] Wrote {OUT_YAML.relative_to(ROOT)}")
    print(f"[scan_material_leaks] Wrote {OUT_MD.relative_to(ROOT)}")
    print(
        f"[scan_material_leaks] summary: files={dart_total} material_any={material_any} "
        f"material_full={material_full} show_only={material_show} clean={no_material}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
