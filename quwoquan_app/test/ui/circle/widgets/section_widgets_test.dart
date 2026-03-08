import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_works.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_chat.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_storage.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_interaction.dart';

Widget _wrap(Widget child) => ProviderScope(
      overrides: [
        circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
      ],
      child: MaterialApp.router(
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
  group('SectionWorks — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SingleChildScrollView(
          child: SectionWorks(circleId: 'circle_photo_01', isDark: false),
        )),
      );
      await tester.pump();
      expect(find.byType(SectionWorks), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SingleChildScrollView(
          child: SectionWorks(circleId: 'empty', isDark: false),
        )),
      );
      await tester.pump();
      expect(find.byType(SectionWorks), findsOneWidget);
    });
  });

  group('SectionChat — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SectionChat(
          circleId: 'circle_photo_01',
          conversationId: 'conv_circle_photo_01',
          isDark: false,
        )),
      );
      await tester.pump();
      expect(find.byType(SectionChat), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SectionChat(
          circleId: 'empty',
          conversationId: null,
          isDark: false,
        )),
      );
      await tester.pump();
      expect(find.byType(SectionChat), findsOneWidget);
    });
  });

  group('SectionStorage — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SectionStorage(
          circleId: 'circle_photo_01',
          isDark: false,
          storageUsedBytes: 52428800,
          storageQuotaBytes: 1073741824,
        )),
      );
      await tester.pump();
      expect(find.byType(SectionStorage), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(SectionStorage(
          circleId: 'empty',
          isDark: false,
          storageUsedBytes: 0,
          storageQuotaBytes: 1073741824,
        )),
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
