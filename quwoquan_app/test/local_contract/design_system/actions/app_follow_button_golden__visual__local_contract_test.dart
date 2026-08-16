@Tags(<String>['serial', 'visual'])
library;

// 关注 pill 双变体双主题的视觉基线（组件级视觉回归）。
//
// 基线更新规范：仅在对应 UI 有意变更的同一变更集内以
// `flutter test --update-goldens <本文件>` 重建，禁止孤立刷基线。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/actions/app_follow_button.dart';

Widget _host({
  required Brightness brightness,
  required AppFollowButtonStyle style,
}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: RepaintBoundary(
      key: ValueKey<String>('follow-${style.name}-${brightness.name}'),
      child: CupertinoPageScaffold(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              AppFollowButton(
                isFollowing: false,
                onPressed: () {},
                style: style,
              ),
              const SizedBox(height: 16),
              AppFollowButton(
                isFollowing: true,
                onPressed: () {},
                style: style,
              ),
            ],
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
    for (final style in AppFollowButtonStyle.values) {
      testWidgets('AppFollowButton ${style.name} ${brightness.name} 视觉基线', (
        tester,
      ) async {
        tester.view.physicalSize = const Size(400, 400);
        tester.view.devicePixelRatio = 2.0;
        addTearDown(tester.view.reset);

        await tester.pumpWidget(_host(brightness: brightness, style: style));
        await tester.pump();

        await expectLater(
          find.byKey(
            ValueKey<String>('follow-${style.name}-${brightness.name}'),
          ),
          matchesGoldenFile(
            'goldens/app_follow_button_${style.name}_${brightness.name}.png',
          ),
        );
      });
    }
  }
}
