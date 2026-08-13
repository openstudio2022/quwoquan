// 骨架 primitives reduce-motion 静止态的双主题视觉基线。
//
// 基线更新规范：仅在对应 UI 有意变更的同一变更集内以
// `flutter test --update-goldens <本文件>` 重建，禁止孤立刷基线。
// 采样固定在 disableAnimations 静止态（峰值透明度），避免 shimmer
// 相位导致基线漂移。
//
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#gwt-003.t1
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';

Widget _host({required Brightness brightness}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: MediaQuery(
      data: const MediaQueryData(disableAnimations: true),
      child: RepaintBoundary(
        key: ValueKey<String>('skeleton-${brightness.name}'),
        child: CupertinoPageScaffold(
          child: Center(
            child: AppSkeletonShimmer(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const AppSkeletonBlock(width: 200, height: 96),
                  const SizedBox(height: 12),
                  const AppSkeletonLine(width: 160),
                  const SizedBox(height: 12),
                  const AppSkeletonCircle(size: 40),
                ],
              ),
            ),
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
    testWidgets('AppSkeleton 静止态 ${brightness.name} 视觉基线', (tester) async {
      tester.view.physicalSize = const Size(500, 600);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_host(brightness: brightness));
      await tester.pump();

      await expectLater(
        find.byKey(ValueKey<String>('skeleton-${brightness.name}')),
        matchesGoldenFile('goldens/app_skeleton_static_${brightness.name}.png'),
      );
    });
  }
}
