@Tags(<String>['serial', 'visual'])
library;

// 共享空态组件的双主题 golden 基线（组件级视觉回归样板）。
//
// 基线更新规范：仅在对应 UI 有意变更的同一变更集内以
// `flutter test --update-goldens <本文件>` 重建，禁止孤立刷基线。
// 文本未加载自定义字体，使用测试环境确定性字形，保证跨机器可比对。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';

Widget _host({required Brightness brightness}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: RepaintBoundary(
      key: ValueKey<String>('empty-state-${brightness.name}'),
      child: const CupertinoPageScaffold(
        child: Center(
          child: AppEmptyState(
            icon: CupertinoIcons.doc_plaintext,
            title: '暂无草稿',
            subtitle: '你的创作会自动保存到这里',
          ),
        ),
      ),
    ),
  );
}

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppEmptyState ${brightness.name} 主题视觉基线', (tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_host(brightness: brightness));
      await tester.pump();

      await expectLater(
        find.byKey(ValueKey<String>('empty-state-${brightness.name}')),
        matchesGoldenFile('goldens/app_empty_state_${brightness.name}.png'),
      );
    });
  }
}
