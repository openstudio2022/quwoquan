import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_repository.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/ui/plaza/pages/connection_hub_page.dart';
import 'package:quwoquan_app/ui/plaza/pages/companion_trip_page.dart';

final class _NoopVisitRecorderService extends VisitRecorderService {
  _NoopVisitRecorderService() : super();

  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

Widget _scopedApp({ConnectionRepository? repository}) {
  return ProviderScope(
    overrides: [
      connectionRepositoryProvider.overrideWithValue(
        repository ?? const MockConnectionRepository(),
      ),
      visitRecorderServiceProvider.overrideWithValue(
        _NoopVisitRecorderService(),
      ),
      isDarkProvider.overrideWithValue(false),
    ],
    child: MaterialApp.router(
      theme: AppTheme.lightTheme,
      routerConfig: GoRouter(
        initialLocation: '/plaza',
        routes: <RouteBase>[
          GoRoute(
            path: '/plaza',
            builder: (_, _) => const Scaffold(body: ConnectionHubPage()),
          ),
          GoRoute(
            path: '/plaza/nearby',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('nearby-affinity-page')),
          ),
          GoRoute(
            path: '/plaza/companion',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('companion-trip-page')),
          ),
          GoRoute(
            path: '/plaza/meetup',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('offline-meetup-page')),
          ),
        ],
      ),
    ),
  );
}

void main() {
  group('ConnectionHubPage', () {
    testWidgets('加载成功：展示标题、四 tab 与同趣列表', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      expect(find.byKey(ConnectionHubPage.viewKey), findsOneWidget);
      expect(find.text(AppConceptConstants.plazaTitle), findsOneWidget);
      expect(find.text(PlazaTextConstants.tabAffinity), findsWidgets);
      expect(find.text(PlazaTextConstants.tabCompanion), findsWidgets);
      expect(find.text('阿曼的山野'), findsOneWidget);
    });

    testWidgets('切换 tab：附近需授权后展示列表', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(PlazaTextConstants.tabNearby));
      await tester.pumpAndSettle();

      expect(find.text(PlazaTextConstants.permissionTitle), findsOneWidget);
      await tester.tap(find.text(PlazaTextConstants.permissionGrant));
      await tester.pumpAndSettle();

      expect(find.text('川西风很大'), findsOneWidget);
    });

    testWidgets('同行 tab 展示结伴列表', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byKey(ConnectionHubPage.segmentKey),
          matching: find.text(PlazaTextConstants.tabCompanion),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('稻城亚丁'), findsWidgets);
      expect(find.text(PlazaTextConstants.seeAllLabel), findsOneWidget);
    });

    testWidgets('结伴页独立路由可渲染', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            connectionRepositoryProvider.overrideWithValue(
              const MockConnectionRepository(),
            ),
            visitRecorderServiceProvider.overrideWithValue(
              _NoopVisitRecorderService(),
            ),
            isDarkProvider.overrideWithValue(false),
          ],
          child: MaterialApp.router(
            theme: AppTheme.lightTheme,
            routerConfig: GoRouter(
              initialLocation: '/plaza/companion',
              routes: <RouteBase>[
                GoRoute(
                  path: '/plaza/companion',
                  builder: (_, _) => const CompanionTripPage(),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(CompanionTripPage.viewKey), findsOneWidget);
      expect(find.text(PlazaTextConstants.companionPageTitle), findsOneWidget);
    });
  });
}
