import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_chat.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_storage.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_interaction.dart';

Widget _wrap(Widget child, {double textScaleFactor = 1.0}) => ProviderScope(
  overrides: [
    circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
  ],
  child: MaterialApp.router(
    builder: (context, childWidget) {
      final mediaQuery = MediaQuery.of(context);
      return MediaQuery(
        data: mediaQuery.copyWith(
          textScaler: TextScaler.linear(textScaleFactor),
        ),
        child: childWidget ?? const SizedBox.shrink(),
      );
    },
    routerConfig: GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => Scaffold(body: child),
        ),
        GoRoute(path: '/article/:id', builder: (_, _) => const SizedBox()),
        GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
      ],
    ),
  ),
);

void main() {
  group('SectionCreations — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'circle_photo_01',
              isDark: false,
              role: CircleRole.owner,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SectionCreations), findsOneWidget);
      expect(find.text('点滴'), findsAtLeastNWidgets(1));
      expect(find.text('作品'), findsWidgets);

      await tester.tap(find.text('作品').first);
      await tester.pumpAndSettle();
      expect(find.text('笔记'), findsOneWidget);
    });

    test('圈子文章 mock 覆盖封面/标题四种组合', () {
      final items = CircleMockData.circleFeedItems
          .where((item) => (item['contentType'] ?? '').toString() == 'article')
          .toList(growable: false);
      bool hasCase({required bool expectCover, required bool expectTitle}) {
        return items.any((raw) {
          final hasCover = (raw['coverUrl'] ?? '').toString().trim().isNotEmpty;
          final hasTitle = (raw['title'] ?? '').toString().trim().isNotEmpty;
          final hasBody = (raw['body'] ?? '').toString().trim().isNotEmpty;
          return hasBody && hasCover == expectCover && hasTitle == expectTitle;
        });
      }

      expect(hasCase(expectCover: true, expectTitle: true), isTrue);
      expect(hasCase(expectCover: false, expectTitle: true), isTrue);
      expect(hasCase(expectCover: true, expectTitle: false), isTrue);
      expect(hasCase(expectCover: false, expectTitle: false), isTrue);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'empty',
              isDark: false,
              role: CircleRole.member,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SectionCreations), findsOneWidget);
    });

    testWidgets('窄高容器空态不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 560);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(
          _wrap(
            const SizedBox(
              height: 220,
              child: SectionCreations(
                circleId: 'empty',
                isDark: false,
                role: CircleRole.owner,
              ),
            ),
            textScaleFactor: 1.3,
          ),
        );
        await tester.pumpAndSettle();
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });

    testWidgets('owner 模式可切换列表视图', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'circle_photo_01',
              isDark: false,
              role: CircleRole.owner,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('列表视图'));
      await tester.pumpAndSettle();

      expect(find.textContaining('赞 '), findsWidgets);
    });

    testWidgets('窄屏大字号下网格卡片不溢出', (tester) async {
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
        await tester.pumpWidget(
          _wrap(
            const SizedBox(
              height: 800,
              child: SectionCreations(
                circleId: 'circle_photo_01',
                isDark: false,
                role: CircleRole.owner,
              ),
            ),
            textScaleFactor: 1.4,
          ),
        );
        await tester.pumpAndSettle();
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });

    testWidgets('笔记双列区分封面卡与文字卡并展示频道推荐', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'circle_photo_01',
              isDark: false,
              role: CircleRole.owner,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('作品').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('笔记'));
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          const ValueKey<String>('circle-article-grid-circle_journal_cover'),
        ),
        findsOneWidget,
      );
      await tester.drag(find.byType(GridView), const Offset(0, -320));
      await tester.pumpAndSettle();
      expect(
        find.byKey(
          const ValueKey<String>('circle-article-grid-circle_ritual_plain'),
        ),
        findsOneWidget,
      );
      expect(find.textContaining('频道推荐'), findsWidgets);
    });
  });

  group('SectionChat — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionChat(
            circleId: 'circle_photo_01',
            conversationId: 'conv_circle_photo_01',
            isDark: false,
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(SectionChat), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionChat(circleId: 'empty', conversationId: null, isDark: false),
        ),
      );
      await tester.pump();
      expect(find.byType(SectionChat), findsOneWidget);
    });
  });

  group('SectionStorage — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionStorage(
            circleId: 'circle_photo_01',
            isDark: false,
            storageUsedBytes: 52428800,
            storageQuotaBytes: 1073741824,
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(SectionStorage), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionStorage(
            circleId: 'empty',
            isDark: false,
            storageUsedBytes: 0,
            storageQuotaBytes: 1073741824,
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(SectionStorage), findsOneWidget);
    });
  });

  group('SectionInteraction — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SectionInteraction(circleId: 'circle_photo_01', isDark: false)),
      );
      await tester.pump();
      expect(find.byType(SectionInteraction), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SectionInteraction(circleId: 'empty', isDark: false)),
      );
      await tester.pump();
      expect(find.byType(SectionInteraction), findsOneWidget);
    });
  });
}
