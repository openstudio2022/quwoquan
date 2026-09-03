# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""原生 runtime config 错误码闭集一致性契约。

`runtime_config_error_codes` 是双端原生可达错误面（MethodChannel、activation
receipt、原生日志错误码）的唯一闭集：

- Android/iOS 原生源码中出现的全部 `runtime_config_*` 完整字符串字面量必须在册：
  或登记为错误码，或是 manifest `schemas:` 闭集的 schema key
  （生成契约 `schemaValues` 的下标访问）；
- 已退役的自由文本 fallback `runtime_config_operation_failed` 不得回归；
- receipt 语义与 rollback「状态未知」语义的关键错误码必须保持在册。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "app_launch_manifest.yaml"
)
ANDROID_SOURCE_DIR = (
    REPO_ROOT
    / "quwoquan_app"
    / "android"
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "quwoquan"
    / "quwoquan_app"
)
IOS_RUNNER_SOURCE_DIR = REPO_ROOT / "quwoquan_app" / "ios" / "Runner"

_CODE_LITERAL = re.compile(r'"(runtime_config_[a-z_]+)"')


def registered_error_codes() -> set[str]:
    codes: set[str] = set()
    inside = False
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("runtime_config_error_codes:"):
            inside = True
            continue
        if inside:
            if line and not line.startswith(" "):
                break
            match = re.match(r"  (runtime_config_[a-z_]+):", line)
            if match:
                codes.add(match.group(1))
    return codes


def registered_schema_keys() -> set[str]:
    """manifest `schemas:` 闭集的 schema key（原生经 schemaValues 下标消费）。"""
    keys: set[str] = set()
    inside = False
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("schemas:"):
            inside = True
            continue
        if inside:
            if line and not line.startswith(" "):
                break
            match = re.match(r"  (runtime_config_[a-z_]+):", line)
            if match:
                keys.add(match.group(1))
    return keys


def native_literal_codes() -> dict[str, set[str]]:
    sources = {
        "android": sorted(ANDROID_SOURCE_DIR.rglob("*.java")),
        "ios": sorted(IOS_RUNNER_SOURCE_DIR.rglob("*.swift")),
    }
    found: dict[str, set[str]] = {}
    for platform, files in sources.items():
        codes: set[str] = set()
        for file in files:
            codes.update(_CODE_LITERAL.findall(file.read_text(encoding="utf-8")))
        found[platform] = codes
    return found


class NativeRuntimeConfigErrorCodeClosedSetTest(unittest.TestCase):
    def test_registered_closed_set_owns_failure_semantics_codes(self) -> None:
        registered = registered_error_codes()
        self.assertGreater(len(registered), 0, "metadata 闭集不得为空")
        for required in (
            "runtime_config_activation_receipt_missing",
            "runtime_config_activation_receipt_read_failed",
            "runtime_config_activation_receipt_malformed",
            "runtime_config_activation_rollback_failed",
            "runtime_config_internal_failure",
        ):
            self.assertIn(required, registered, f"闭集缺少失败语义错误码 {required}")

    def test_native_error_literals_are_all_registered(self) -> None:
        registered = registered_error_codes()
        schema_keys = registered_schema_keys()
        self.assertGreater(len(schema_keys), 0, "manifest schemas 闭集不得为空")
        # schema key 与错误码是两个不相交闭集：任何一侧不得冒用另一侧命名。
        self.assertEqual(sorted(registered & schema_keys), [])
        for platform, codes in native_literal_codes().items():
            self.assertGreater(len(codes), 0, f"{platform} 原生错误码采集不得为空")
            unregistered = sorted(codes - registered - schema_keys)
            self.assertEqual(
                unregistered,
                [],
                f"{platform} 原生源码存在未登记 runtime_config 错误码：{unregistered}",
            )

    def test_retired_free_text_fallback_never_returns(self) -> None:
        for platform, codes in native_literal_codes().items():
            self.assertNotIn(
                "runtime_config_operation_failed",
                codes,
                f"{platform} 不得恢复已退役的自由文本 fallback 错误码",
            )


if __name__ == "__main__":
    unittest.main()
