import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/navigation/app_router_gathering_routes.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

void main() {
  group('Gathering app shell routes', () {
    testWidgets('create generated route 可达且缺 Host authority 时结构化失败', (
      tester,
    ) async {
      await _pumpRoute(tester, AppRoutePaths.gatheringCreate);

      expect(find.byType(GatheringCreateRouteHost), findsOneWidget);
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

      expect(find.byType(GatheringDetailRouteHost), findsOneWidget);
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

      expect(find.byType(GatheringBoardRouteHost), findsOneWidget);
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
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
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
  await tester.pump();

  expect(
    router.routeInformationProvider.value.uri.path,
    Uri.parse(location).path,
  );
  expect(find.byType(GatheringRouteUnavailableState), findsOneWidget);
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
