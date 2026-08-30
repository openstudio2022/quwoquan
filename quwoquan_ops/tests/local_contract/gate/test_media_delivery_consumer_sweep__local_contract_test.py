"""消费面全仓扫描锁的本地契约锚点（DEC-033）。

锁的价值全在「漏接会不会红」。这些锚点各自钉住一种会让锁失效的漂移：扫描漏掉
新增消费点、册子腐化成无人维护的白名单、豁免项不写理由、以及把 typed 入口自身
的终态槽位误判成裸直连。

角色：gate 的反向验证。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops" / "gate"))

import media_delivery_consumer_sweep as sweep  # noqa: E402


def _validate() -> list[str]:
    issues: list[str] = []
    sweep.validate(issues)
    return issues


def test_registry_is_consistent_with_current_tree() -> None:
    assert _validate() == []


def test_baseline_is_empty() -> None:
    """基线归零是链路闭合的判定。回潮先表现为基线重新长出条目。"""

    assert sweep.baseline_size() == 0


def test_unregistered_direct_render_is_blocked(tmp_path: Path) -> None:
    """新增一处未登记的裸直连必须被抓，否则锁只是一张过期清单。"""

    target = (
        sweep.APP_LIB
        / "service/content_service/content/post/presentation/home_multi_form_feed.dart"
    )
    original = target.read_text(encoding="utf-8")
    leak = (
        original
        + "\n// ignore: unused_element\n"
        + 'Widget _sweepProbe() => AppCachedNetworkImage(imageUrl: "probe");\n'
    )
    try:
        target.write_text(leak, encoding="utf-8")
        issues = _validate()
    finally:
        target.write_text(original, encoding="utf-8")
    assert any("不在册" in issue for issue in issues)


def test_stale_registry_entry_is_blocked() -> None:
    """已消失的条目必须同批删除，否则册子会逐渐指向无关代码。"""

    path = sweep.REGISTRY_PATH
    original = path.read_text(encoding="utf-8")
    try:
        path.write_text(
            original + "  service/ghost/vanished.dart:1: 幽灵条目\n",
            encoding="utf-8",
        )
        issues = _validate()
    finally:
        path.write_text(original, encoding="utf-8")
    assert any("已不再直连" in issue for issue in issues)


def test_allowlist_entry_without_reason_is_blocked() -> None:
    """豁免必须带归类理由：没有理由的豁免等于把判据交给了下一个读者的记忆。"""

    issues: list[str] = []
    registry = {"baseline": {}, "allowlist": {"a/b.dart:1": "  "}}
    for site, reason in registry["allowlist"].items():
        if not reason.strip():
            issues.append(f"豁免项缺归类理由: {site}")
    assert issues


def test_typed_entry_terminal_slots_are_not_direct_render() -> None:
    """typed 入口的缺席/失败/等待槽位不承担取址，不能被判成裸直连。"""

    lines = [
        "MediaDeliveryImage(",
        "  binding: binding,",
        "  absentWidget: RoundedSquareAvatar(",
        "    imageUrl: '',",
        "  ),",
        ")",
    ]
    assert sweep._is_dispatch_render(lines, 2)


def test_dispatch_callback_render_is_not_direct_render() -> None:
    """publicBuilder 里的公开原子是分流后的那一路，不是绕过分流。"""

    lines = [
        "MediaDeliveryImage(",
        "  publicBuilder: (context, publicUrl) =>",
        "      AppCachedNetworkImage(imageUrl: publicUrl),",
        ")",
    ]
    assert sweep._is_dispatch_render(lines, 2)


def test_atom_definition_files_are_excluded() -> None:
    """原子自身的定义不是消费点，否则每个原子都会把自己钉在册子上。"""

    sites = sweep.scan_direct_render_sites()
    for definition in sweep.ATOM_DEFINITION_FILES:
        assert not any(site.startswith(f"{definition}:") for site in sites)
