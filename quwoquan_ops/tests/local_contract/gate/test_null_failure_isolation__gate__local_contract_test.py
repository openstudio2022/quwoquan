"""空引用隔离门禁自身的行为契约。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#req-004

这道门禁没有 allowlist 也没有基线，所以它的判定边界就是唯一的旋钮——判错一次，
要么放过真实缺陷，要么把无关代码逼进豁免。两边都要钉住：

* 反例先行。`actionError: () => null` 是 `copyWith` 的可空字段更新，与 catch 无关，
  而它恰好包含 `onError` 子串——扩展扫描时如果不带词边界就会误报，误报又会逼出
  allowlist，而规则明令禁止新增 allowlist。
* `return false` 明确划在范围之外。它没有把失败压成缺席或空值，调用方也不会把
  `false` 读成成功；异常被吞掉这件事由吞错预算门禁承担。两道门重叠只会让同一段
  代码得到两个结论。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = (
    ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "observability"
    / "verify_null_failure_isolation.py"
)


def _load_gate():
    scripts_root = ROOT / "quwoquan_app" / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    spec = importlib.util.spec_from_file_location(
        "verify_null_failure_isolation", GATE_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载门禁: {GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NullFailureIsolationBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_gate()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app_root = Path(temporary.name)
        self.lib_root = self.app_root / "lib"
        self.lib_root.mkdir(parents=True)
        self.module.APP_ROOT = self.app_root
        self.module.LIB_ROOT = self.lib_root

    def _write(self, source: str, relative: str = "service/probe.dart") -> None:
        path = self.lib_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def _run(self) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = self.module.main()
        return code, stdout.getvalue()

    def assertPasses(self) -> None:
        code, output = self._run()
        self.assertEqual(code, 0, f"应通过但被判违规:\n{output}")

    def assertBlocks(self, expected: str) -> None:
        code, output = self._run()
        self.assertEqual(code, 1, f"应被拦下但通过了:\n{output}")
        self.assertIn(expected, output)

    def test_nullable_field_update_callback_is_not_error_handling(self) -> None:
        self._write(
            """
class Settings {
  Settings copyWith({ValueGetter<Object?>? actionError}) => this;
}

Settings clearError(Settings settings) =>
    settings.copyWith(actionError: () => null);
"""
        )
        self.assertPasses()

    def test_try_prefixed_parser_may_return_null(self) -> None:
        self._write(
            """
Object? _tryDecodeBody(String body) {
  try {
    return jsonDecode(body);
  } catch (_) {
    return null;
  }
}
"""
        )
        self.assertPasses()

    def test_degradation_with_recorded_evidence_passes(self) -> None:
        self._write(
            """
Future<Box<String>?> openBox(String name) async {
  try {
    return await Hive.openBox<String>(name);
  } catch (error, stackTrace) {
    developer.log('open failed', name: 'x', error: error, stackTrace: stackTrace);
    return null;
  }
}
"""
        )
        self.assertPasses()

    def test_returning_false_belongs_to_the_swallow_budget_gate(self) -> None:
        self._write(
            """
Future<bool> leaveCircle(String id) async {
  try {
    await remote.leave(id);
    return true;
  } catch (_) {
    return false;
  }
}
"""
        )
        self.assertPasses()

    def test_conditional_absence_with_rethrow_for_real_failures_passes(self) -> None:
        """只有「不可见」返回 null，其余错误重新抛出——失败仍有表达路径。"""
        self._write(
            """
Future<Detail?> loadDetail(String id, {required bool allowFallback}) {
  return client.fetch(id).then<Detail?>(
    (wire) => wire,
    onError: (Object error, StackTrace stackTrace) {
      if (allowFallback && error is CloudException && error.type == notFound) {
        return null;
      }
      return Future<Detail?>.error(error, stackTrace);
    },
  );
}
"""
        )
        self.assertPasses()

    def test_zero_guard_with_failure_surfaced_into_state_passes(self) -> None:
        """`return 0` 是卸载守卫，失败本身已经写进了 state.error。"""
        self._write(
            """
Future<int> loadOlder(String id) async {
  try {
    if (!ref.mounted) return 0;
    return merged.length - previousCount;
  } catch (caught) {
    if (!ref.mounted) return 0;
    state = state.copyWith(error: runtimeErrorDisplayMessage(caught));
    return state.messages.length - previousCount;
  }
}
"""
        )
        self.assertPasses()

    def test_bare_catch_returning_null_without_evidence_blocks(self) -> None:
        self._write(
            """
Future<Profile?> loadProfile(String id) async {
  try {
    return await remote.fetch(id);
  } catch (_) {
    return null;
  }
}
"""
        )
        self.assertBlocks("loadProfile")

    def test_catch_error_callback_returning_null_without_evidence_blocks(self) -> None:
        self._write(
            """
Future<Profile?> preload(String id) {
  return remote.fetch(id).catchError((_) => null);
}
"""
        )
        self.assertBlocks("preload")

    def test_on_error_named_argument_returning_null_blocks(self) -> None:
        self._write(
            """
Future<Profile?> preload(String id) {
  return remote.fetch(id).then((value) => value, onError: (error, stack) => null);
}
"""
        )
        self.assertBlocks("preload")

    def test_catch_returning_empty_list_without_evidence_blocks(self) -> None:
        self._write(
            """
Future<List<Emoji>> recent() async {
  try {
    return await store.readRecent();
  } catch (_) {
    return [];
  }
}
"""
        )
        self.assertBlocks("recent")

    def test_catch_returning_empty_map_without_evidence_blocks(self) -> None:
        self._write(
            """
Map<String, int> decodeCounts(String raw) {
  try {
    return Map<String, int>.from(jsonDecode(raw) as Map);
  } catch (_) {
    return {};
  }
}
"""
        )
        self.assertBlocks("decodeCounts")

    def test_catch_returning_zero_without_evidence_blocks(self) -> None:
        self._write(
            """
Future<int> loadOlderMessages(String id) async {
  try {
    return await remote.loadOlder(id);
  } catch (_) {
    return 0;
  }
}
"""
        )
        self.assertBlocks("loadOlderMessages")

    def test_typed_empty_list_literal_is_also_a_disguise(self) -> None:
        self._write(
            """
Future<List<Failure>> loadQueue() async {
  try {
    return await store.readQueue();
  } catch (_) {
    return <Failure>[];
  }
}
"""
        )
        self.assertBlocks("loadQueue")

    def test_empty_collection_with_evidence_passes(self) -> None:
        self._write(
            """
Future<List<Emoji>> recent() async {
  try {
    return await store.readRecent();
  } catch (error, stackTrace) {
    developer.log('recent failed', name: 'x', error: error, stackTrace: stackTrace);
    return [];
  }
}
"""
        )
        self.assertPasses()


if __name__ == "__main__":
    unittest.main()
