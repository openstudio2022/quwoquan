@Tags(<String>['serial', 'visual'])
library;

// 原视频书图标与中央按钮的有意视觉变更，同批更新并人工核对基线。
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-layout-semantics/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-001.t2

import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';

import '../../../support/runtime/bottom_navigation_test_host.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    // 从构建产物的字体清单取路径，不绑定开发机 pub cache。
    final manifest = jsonDecode(
      await rootBundle.loadString('FontManifest.json'),
    ) as List<dynamic>;
    for (final entry in manifest.cast<Map<String, dynamic>>()) {
      final family = entry['family'] as String;
      if (family != 'Noto Sans SC' &&
          !family.contains('CupertinoIcons') &&
          !family.toLowerCase().contains('fluent')) {
        continue;
      }
      final loader = FontLoader(family);
      for (final font
          in (entry['fonts'] as List<dynamic>).cast<Map<String, dynamic>>()) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
  });

  for (final brightness in Brightness.values) {
    testWidgets('移动底栏 ${brightness.name} 原图标与横向中央操作视觉基线', (tester) async {
      tester.view.physicalSize = const Size(820, 500);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      const boundaryKey = ValueKey<String>('bottom-navigation-visual');
      await tester.pumpWidget(
        bottomNavigationTestHost(
          brightness: brightness,
          child: RepaintBoundary(
            key: boundaryKey,
            child: ColoredBox(
              color: brightness == Brightness.dark
                  ? CupertinoColors.black
                  : CupertinoColors.white,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final configuration in [
                    (width: 320.0, inset: 0.0, scale: 1.0, index: 0),
                    (width: 393.0, inset: 34.0, scale: 1.0, index: 1),
                    (width: 393.0, inset: 34.0, scale: 2.0, index: 3),
                    (width: 820.0, inset: 0.0, scale: 1.0, index: 4),
                  ])
                    Builder(
                      builder: (context) {
                        return MediaQuery(
                          data: MediaQuery.of(context).copyWith(
                            size: Size(configuration.width, 900),
                            viewPadding: EdgeInsets.only(
                              bottom: configuration.inset,
                            ),
                            padding: EdgeInsets.only(
                              bottom: configuration.inset,
                            ),
                            textScaler: TextScaler.linear(configuration.scale),
                          ),
                          child: SizedBox(
                            width: configuration.width,
                            child: DefaultTextStyle(
                              style: const TextStyle(
                                fontFamily: 'Noto Sans SC',
                              ),
                              child: BottomNavigationWidget(
                                currentIndex: configuration.index,
                                onTap: (_) {},
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await expectLater(
        find.byKey(boundaryKey),
        matchesGoldenFile('goldens/bottom_navigation_${brightness.name}.png'),
      );
    });
  }
}
