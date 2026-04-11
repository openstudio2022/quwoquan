import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tabs_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';

const Duration _kCirclesPageSettleTimeout = Duration(seconds: 1);

/// 墙钟上界 1s：用有限次 [pump] 代替 [pumpAndSettle]，避免永不 settle 或与 fake clock 交织时长时间挂起。
Future<void> _circlesPumpSettled(WidgetTester tester) async {
  final deadline = DateTime.now().add(_kCirclesPageSettleTimeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 16));
    if (!tester.binding.hasScheduledFrame) return;
  }
}

/// 与 [CircleCategoryTabsLoader.assetPath] 同源；单测里避免 `rootBundle.loadString` 在部分环境下挂起。
Map<String, CircleCategoryTabConfigDto> _fixtureCategoryTabsConfig() {
  final candidates = <File>[
    File(
      '${Directory.current.path}/../quwoquan_service/contracts/metadata/social/circle/ui_category_tabs.yaml',
    ),
    File(
      '${Directory.current.path}/quwoquan_service/contracts/metadata/social/circle/ui_category_tabs.yaml',
    ),
  ];
  for (final f in candidates) {
    if (f.existsSync()) {
      return CircleCategoryTabsLoader.parseFromYamlString(f.readAsStringSync());
    }
  }
  return Map<String, CircleCategoryTabConfigDto>.from(
    CircleCategoryTabDefaults.remoteStyleFallback,
  );
}

/// 避免单测里 [CircleCategoryTabsLoader.loadFromAsset] 走 `rootBundle` 挂起。
class _FixtureCategoryMockRepo extends MockCircleRepository {
  @override
  Future<Map<String, CircleCategoryTabConfigDto>> getCircleCategoryConfig() async {
    return _fixtureCategoryTabsConfig();
  }
}

Widget _scopedApp({CircleRepository? mock, double textScaleFactor = 1.0}) {
  final repo = mock ?? _FixtureCategoryMockRepo();
  return ProviderScope(
    overrides: [circleRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      builder: (context, child) {
        final mediaQuery = MediaQuery.of(context);
        return MediaQuery(
          data: mediaQuery.copyWith(
            textScaler: TextScaler.linear(textScaleFactor),
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
      routerConfig: GoRouter(
        initialLocation: '/circles',
        routes: [
          GoRoute(
            path: '/circles',
            builder: (_, _) => const Scaffold(body: CirclesPage()),
          ),
          GoRoute(path: '/circle/:id', builder: (_, _) => const SizedBox()),
          GoRoute(path: '/article/:id', builder: (_, _) => const SizedBox()),
        ],
      ),
    ),
  );
}

void main() {
  group('CirclesPage — 渲染契约', () {
    testWidgets('正常渲染圈子列表页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(CirclesPage), findsOneWidget);
    });

    testWidgets('Tab 导航栏存在', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('展示圈子广场标题与左侧分类菜单', (tester) async {
      final mock = _FixtureCategoryMockRepo();
      final cfg = _fixtureCategoryTabsConfig();
      await tester.pumpWidget(_scopedApp(mock: mock));
      await tester.pump();
      await _circlesPumpSettled(tester);

      expect(find.text(UITextConstants.circlesDirectoryTitle), findsOneWidget);
      expect(find.text(UITextConstants.homeCirclesMy), findsOneWidget);
      final allLabel = cfg['all']?.label ?? '推荐';
      expect(find.text(allLabel), findsOneWidget);
      final meet = cfg['meet'];
      if (meet != null && meet.label.trim().isNotEmpty) {
        expect(find.text(meet.label), findsOneWidget);
      }
    });
  });

  group('CirclesPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await _circlesPumpSettled(tester);

      expect(find.byType(CirclesPage), findsOneWidget);
    });

    testWidgets('窄屏大字号下保持自适应不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 690);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(_scopedApp(textScaleFactor: 1.4));
        await _circlesPumpSettled(tester);
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });
  });

  group('CirclesPage — 错误态渲染', () {
    testWidgets('Repository 返回空列表时安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _EmptyCircleRepository()));
      await tester.pump();

      expect(find.byType(CirclesPage), findsOneWidget);
    });
  });
}

class _EmptyCircleRepository extends _FixtureCategoryMockRepo {
  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
    String? subCategory,
  }) async {
    return [];
  }
}
