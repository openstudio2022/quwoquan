import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider;
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart'
    show gatheringQueryReaderProvider;
import 'package:quwoquan_app/runtime/di/navigation/app_router_gathering_routes.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/route_unavailable_state.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/gathering_board_route_host.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_route_hosts.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import '../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  group('Gathering app shell routes', () {
    testWidgets('create generated route 可达且缺 Host authority 时结构化失败', (
      tester,
    ) async {
      await _pumpRoute(tester, AppRoutePaths.gatheringCreate);

      expect(find.byType(GatheringCreatePageRouteHost), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('gatheringCreate-route-unavailable')),
        findsOneWidget,
      );
    });

    testWidgets('detail generated 动态路由可达且缺 query adapter 时结构化失败', (
      tester,
    ) async {
      await _pumpRoute(
        tester,
        AppRoutePaths.gatheringDetail(id: 'gathering-1'),
      );

      expect(find.byType(GatheringDetailPageRouteHost), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('gatheringDetail-route-unavailable')),
        findsOneWidget,
      );
    });

    testWidgets('board generated 动态路由按 conversationId 可达且缺 adapter 时结构化失败', (
      tester,
    ) async {
      await _pumpRoute(
        tester,
        AppRoutePaths.gatheringBoard(id: 'conversation-1'),
      );

      expect(find.byType(GatheringBoardPageRouteHost), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('gatheringBoard-route-unavailable')),
        findsOneWidget,
      );
    });
  });
}

Future<void> _pumpRoute(WidgetTester tester, String location) async {
  final container = ProviderContainer(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'persona-1',
          ownerUserId: 'owner-1',
          displayName: '测试用户',
          avatarUrl: '',
          personaSnapshotVersion: 0,
        ),
      ),
      gatheringQueryReaderProvider.overrideWith(
        (_) => throw StateError('GatheringQueryReader unavailable'),
      ),
    ],
  );
  final router = GoRouter(
    initialLocation: location,
    routes: <RouteBase>[
      ...gatheringRoutes(),
      GoRoute(
        path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) => const SizedBox.shrink(),
        routes: <RouteBase>[gatheringBoardRoute()],
      ),
    ],
  );
  addTearDown(() {
    router.dispose();
    container.dispose();
  });

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: CupertinoApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();

  expect(
    router.routeInformationProvider.value.uri.path,
    Uri.parse(location).path,
  );
  expect(find.byType(RouteUnavailableState), findsOneWidget);
  expect(find.text('Page Not Found'), findsNothing);
}

final class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'owner-1',
      activePersonaId: 'persona-1',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-1',
    );
  }
}
