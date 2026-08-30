"""release 媒体消费面的全仓扫描（DEC-033）。

枚举式 sealed 清单挡不住遗漏：它只盯已经收口的那几个文件，新增或从未被想起的
消费点不在清单里，于是「私有资产走公开 URL」这类漏接永远不会红。逐轮补清单的
结果是每轮都宣称收完、每轮又被翻出新的一批。

本模块把判据反过来：扫 `quwoquan_app/lib` 下**全部**直连公开渲染原子的位置，
每一处都必须落到两个册子之一——

- `baseline`：已知未收口的 release 媒体消费点。修一处删一条，归零即链路闭合。
- `allowlist`：按设计不消费 release 交付的位置（本地草稿、上传预览、通话头像等），
  逐条带归类理由。

不在册的命中直接 BLOCK。这样「新增一个消费面忘了接 typed 绑定」在门禁上就是
硬失败，而不是等到 research 相位真机上看见一片空白才发现。

角色：gate library。由 `verify_media_delivery_contract` 调用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
APP_LIB = ROOT / "quwoquan_app" / "lib"
REGISTRY_PATH = (
    ROOT / "quwoquan_ops" / "policies" / "gates" / "media_delivery_consumer_sweep.yaml"
)

# 直连即绕过 typed 分流的公开渲染原子。
PUBLIC_RENDER_ATOMS = (
    "AppCachedNetworkImage",
    "AppMediaImage",
    "AppAvatarImage",
    "AppCircularAvatar",
    "RoundedSquareAvatar",
    "ArticleAdaptiveImage",
)

# 原子自身的定义文件：类声明与内部实现不是消费点。
ATOM_DEFINITION_FILES = frozenset(
    {
        "design_system/media/app_cached_network_image.dart",
        "design_system/media/app_media_image.dart",
        "design_system/avatar/rounded_square_avatar.dart",
        "service/content_service/content/post/presentation/article_content_block_renderer.dart",
    }
)

# 分流已经发生的合法渲染位。前三个是 typed 入口把已定的那一路交回消费面渲染；
# 后三个是 typed 入口自身的终态槽位（缺席/失败/等待），它们不承担取址，渲染的是
# 与 URL 无关的兜底件。
DISPATCH_CALLBACKS = (
    "publicBuilder",
    "readyBuilder",
    "signedReadyBuilder",
    "absentWidget",
    "errorWidget",
    "placeholder",
)

# 回调声明与其渲染体常跨行（`publicBuilder: (context, url) =>` 换行后才是原子），
# 因此按窗口回看而不是只看命中行。窗口取 4 行：够覆盖格式化后的回调头，又不至于
# 把上一个语句的回调误算成本处的豁免。
DISPATCH_LOOKBACK_LINES = 4

_ATOM_CALL = re.compile(r"\b(" + "|".join(PUBLIC_RENDER_ATOMS) + r")\s*\(")


def _is_dispatch_render(lines: list[str], index: int) -> bool:
    start = max(0, index - DISPATCH_LOOKBACK_LINES)
    window = "\n".join(lines[start : index + 1])
    return any(callback in window for callback in DISPATCH_CALLBACKS)


def scan_direct_render_sites(app_lib: Path = APP_LIB) -> list[str]:
    """返回全部直连命中，形如 `relative/path.dart:line`，按路径行号排序。"""

    sites: list[str] = []
    for path in sorted(app_lib.rglob("*.dart")):
        relative = path.relative_to(app_lib).as_posix()
        if relative in ATOM_DEFINITION_FILES:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not _ATOM_CALL.search(line):
                continue
            if _is_dispatch_render(lines, index):
                continue
            sites.append(f"{relative}:{index + 1}")
    return sites


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"消费面扫描册缺席: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: 扫描册必须是 mapping")
    return payload


def _registry_entries(registry: dict[str, Any], section: str) -> dict[str, str]:
    entries = registry.get(section) or {}
    if not isinstance(entries, dict):
        raise ValueError(f"扫描册 {section} 必须是 site -> reason 的 mapping")
    return {str(site): str(reason or "").strip() for site, reason in entries.items()}


def validate(issues: list[str]) -> None:
    """命中未在册即 BLOCK；在册却已消失的条目同样 BLOCK（防止册子腐化）。"""

    try:
        registry = load_registry()
    except (OSError, ValueError, yaml.YAMLError) as error:
        issues.append(f"消费面扫描册不可读: {error}")
        return

    baseline = _registry_entries(registry, "baseline")
    allowlist = _registry_entries(registry, "allowlist")

    overlap = sorted(set(baseline) & set(allowlist))
    if overlap:
        issues.append(
            "同一消费点不能既是待收口缺口又是豁免项: " + ", ".join(overlap[:5])
        )

    for site, reason in allowlist.items():
        if not reason:
            issues.append(
                f"豁免项缺归类理由: {site}——必须写明为何该处不消费 release 交付"
            )

    found = set(scan_direct_render_sites())
    registered = set(baseline) | set(allowlist)

    unregistered = sorted(found - registered)
    for site in unregistered:
        issues.append(
            f"{site} 直连公开渲染原子且不在册；release 媒体消费点必须经 typed 交付"
            "入口分流，按设计不消费 release 交付则登记为带理由的豁免项"
        )

    # 行号漂移会让册子逐渐指向无关代码，因此消失的条目必须同批删除或更新。
    stale = sorted(registered - found)
    for site in stale:
        issues.append(
            f"{site} 已不再直连公开渲染原子，请从扫描册删除该条目（已收口即减基线）"
        )


def baseline_size() -> int:
    registry = load_registry()
    return len(_registry_entries(registry, "baseline"))
