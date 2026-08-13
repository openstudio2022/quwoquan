"""端侧对象化架构门禁的规则 ID、路径与词法常量（唯一定义处）。"""

from __future__ import annotations

import re
from pathlib import Path

from quwoquan_ops.gate import object_path_map as opm

ROOT = Path(__file__).resolve().parents[3]

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
