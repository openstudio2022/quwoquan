#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-007
"""
verify_app_cohesion_ratchet.py

端侧内聚度棘轮：三类结构债只允许减少，不允许增加。

被棘轮化的债务（每一项都是「架构债」而不是「风格偏好」）：

1. ``di_presentation_files``
   ``quwoquan_app/lib/runtime/di/presentation/**`` 下的 Dart 文件数。
   composition root 只应做装配；业务 Widget 落在这里意味着页面没有归属到
   ``lib/service/<service>/<context>/<object>/presentation/``，对象边界失真。

2. ``objects_missing_layer`` / ``objects_presentation_without_domain``
   App 对象「缺层」计数。对象目录一旦在磁盘上存在，就应当能说明它的
   ``domain / application / adapters / presentation`` 四层归属；其中
   「``domain`` 为 0 但 ``presentation`` 大于 0」是最强的信号——UI 存在、领域模型
   缺席，页面只能直接消费弱类型 wire 形状或把领域规则写进 Widget。

3. ``client_empty_directories``
   端侧空目录数。空目录是搬迁未收尾的残留，会让「目录即树」的归属推导出现
   没有 owner 的节点。

## 为什么棘轮值内联在脚本里

仓库 ``AGENTS.md`` 禁止提交独立的债务台账/inventory 文件。棘轮上限因此作为
本脚本的常量存在，天然随代码评审一起变化：**只允许调小**。任何调大都是在
用门禁换通过，属于明确违规。

## 用法

    python3 quwoquan_app/scripts/runtime/architecture/verify_app_cohesion_ratchet.py
    python3 .../verify_app_cohesion_ratchet.py --app-root /tmp/fixture-app
    python3 .../verify_app_cohesion_ratchet.py --report   # 只打印实测值

``--app-root`` 只服务本脚本自己的 local_contract 负例，不是缩小生产扫描范围的
逃逸口：不传时固定扫描仓库内的 ``quwoquan_app``。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT  # noqa: E402

import argparse  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

#: App 对象的四个 canonical 分层目录名。
APP_OBJECT_LAYERS = ("domain", "application", "adapters", "presentation")

#: 棘轮上限：由本脚本对 App 物理树实时测量，治理 owner 为上述 GWT-007，**只减不增**。
#: 采集时间点的实测值（`--report` 可复现）：
#:   di_presentation_files             = 4
#:   objects_missing_layer             = 62   （82 个对象中缺至少一层）
#:   objects_presentation_without_domain = 17 （domain=0 且 presentation>0）
#:   client_empty_directories          = 0
RATCHET_CEILINGS = {
    "di_presentation_files": 4,
    "objects_missing_layer": 62,
    "objects_presentation_without_domain": 17,
    "client_empty_directories": 0,
}

#: 端侧空目录扫描根（相对 app root）。
EMPTY_DIRECTORY_SCAN_ROOTS = ("lib", "test")

#: 空目录扫描时跳过的、非源码语义的目录名。
SKIPPED_DIRECTORY_NAMES = frozenset(
    {".dart_tool", ".git", "build", ".idea", "__pycache__"}
)


class CohesionScanError(RuntimeError):
    """扫描输入本身不可信时抛出，不得降级为「0 违规」。"""


@dataclass(frozen=True)
class ObjectLayerCounts:
    """单个 App 对象在四层上的文件数。"""

    object_id: str
    counts: dict[str, int]

    @property
    def missing_layers(self) -> tuple[str, ...]:
        return tuple(layer for layer in APP_OBJECT_LAYERS if self.counts[layer] == 0)

    @property
    def presentation_without_domain(self) -> bool:
        return self.counts["domain"] == 0 and self.counts["presentation"] > 0


@dataclass
class CohesionReport:
    metrics: dict[str, int] = field(default_factory=dict)
    objects: list[ObjectLayerCounts] = field(default_factory=list)
    empty_directories: list[str] = field(default_factory=list)


def _dart_file_count(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.rglob("*.dart") if path.is_file())


def scan_di_presentation_files(app_root: Path) -> int:
    """composition root 里残留的业务 Widget 文件数。"""
    return _dart_file_count(app_root / "lib" / "runtime" / "di" / "presentation")


def scan_app_objects(app_root: Path) -> list[ObjectLayerCounts]:
    """从物理树派生 App 对象及其分层文件数。

    对象形状固定为 ``lib/service/<service>/<context>/<object>/<layer>/**``；
    四层全空的目录不算对象（它是 context 级中间目录或搬迁残留）。
    """
    service_root = app_root / "lib" / "service"
    if not service_root.is_dir():
        raise CohesionScanError(f"App service root not found: {service_root}")

    objects: list[ObjectLayerCounts] = []
    for service in sorted(p for p in service_root.iterdir() if p.is_dir()):
        for context in sorted(p for p in service.iterdir() if p.is_dir()):
            for obj in sorted(p for p in context.iterdir() if p.is_dir()):
                counts = {
                    layer: _dart_file_count(obj / layer) for layer in APP_OBJECT_LAYERS
                }
                if sum(counts.values()) == 0:
                    continue
                objects.append(
                    ObjectLayerCounts(
                        object_id=f"{service.name}/{context.name}/{obj.name}",
                        counts=counts,
                    )
                )
    return objects


def scan_empty_directories(app_root: Path) -> list[str]:
    """端侧空目录（不含任何文件的目录，允许含空子目录时逐层各记一次）。"""
    empty: list[str] = []
    for scan_root_name in EMPTY_DIRECTORY_SCAN_ROOTS:
        scan_root = app_root / scan_root_name
        if not scan_root.is_dir():
            continue
        for directory in sorted(scan_root.rglob("*")):
            if not directory.is_dir():
                continue
            if any(part in SKIPPED_DIRECTORY_NAMES for part in directory.parts):
                continue
            if not any(directory.iterdir()):
                empty.append(directory.relative_to(app_root).as_posix())
    return empty


def build_report(app_root: Path) -> CohesionReport:
    if not app_root.is_dir():
        raise CohesionScanError(f"App root not found: {app_root}")

    objects = scan_app_objects(app_root)
    if not objects:
        raise CohesionScanError(
            f"scanned 0 App objects under {app_root}/lib/service; "
            "扫描输入不可信，拒绝把空扫描当成 0 违规"
        )

    empty_directories = scan_empty_directories(app_root)
    report = CohesionReport(objects=objects, empty_directories=empty_directories)
    report.metrics = {
        "di_presentation_files": scan_di_presentation_files(app_root),
        "objects_missing_layer": sum(1 for o in objects if o.missing_layers),
        "objects_presentation_without_domain": sum(
            1 for o in objects if o.presentation_without_domain
        ),
        "client_empty_directories": len(empty_directories),
    }
    return report


def evaluate(report: CohesionReport) -> list[str]:
    """返回超出棘轮上限的说明；空列表表示通过。"""
    regressions: list[str] = []
    for metric, ceiling in sorted(RATCHET_CEILINGS.items()):
        actual = report.metrics[metric]
        if actual > ceiling:
            regressions.append(
                f"{metric}: {actual} > 棘轮上限 {ceiling}（只减不增，禁止调大上限）"
            )
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify App cohesion ratchet")
    parser.add_argument(
        "--app-root",
        default=None,
        help="App root to scan (default: <repo>/quwoquan_app; 仅供本脚本负例测试使用)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="打印实测值与明细，不做棘轮判定",
    )
    args = parser.parse_args(argv)

    app_root = (
        Path(args.app_root).resolve()
        if args.app_root is not None
        else REPO_ROOT / "quwoquan_app"
    )

    try:
        report = build_report(app_root)
    except CohesionScanError as exc:
        print(f"verify_app_cohesion_ratchet: ERROR {exc}", file=sys.stderr)
        return 1

    for metric, ceiling in sorted(RATCHET_CEILINGS.items()):
        print(f"  {metric}: {report.metrics[metric]} (ceiling {ceiling})")

    if args.report:
        print("\n-- objects missing at least one layer --")
        for obj in report.objects:
            if obj.missing_layers:
                print(f"  {obj.object_id}: missing {', '.join(obj.missing_layers)}")
        print("\n-- empty directories --")
        for directory in report.empty_directories:
            print(f"  {directory}")
        return 0

    regressions = evaluate(report)
    if regressions:
        for line in regressions:
            print(f"verify_app_cohesion_ratchet: {line}", file=sys.stderr)
        print(
            "\nverify_app_cohesion_ratchet: 端侧内聚度回退已被阻断",
            file=sys.stderr,
        )
        return 1

    print("verify_app_cohesion_ratchet: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
