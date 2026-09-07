// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-001.t3

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/runtime/shell/object_detail_global_bottom_nav.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

/// 对象详情页（圈子 / 实体主页）底部全局导航栏的根目的地合约。
///
/// 详情页不属于任何底栏 tab；点击第 2 项必须以 `context.go` 落回 canonical
/// `/video-book` 根目的地，而不是 push 出第二个视频书实例。
void main() {
  const detailLocation = '/circle/fixture-circle';

  GoRouter buildRouter() {
    return GoRouter(
      initialLocation: detailLocation,
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (_, _) => const Scaffold(body: Center(child: Text('HOME'))),
        ),
        GoRoute(
          path: AppRoutePaths.videoBook,
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('VIDEO_BOOK_ROOT'))),
        ),
        GoRoute(
          path: AppRoutePaths.circleDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, _) => const Scaffold(
            body: Center(child: Text('OBJECT_DETAIL')),
            bottomNavigationBar: ObjectDetailGlobalBottomNav(),
          ),
        ),
      ],
    );
  }

  Widget buildApp(GoRouter router) {
    return ProviderScope(
      overrides: [
        authSessionControllerProvider.overrideWith(_GuestSession.new),
      ],
      child: MaterialApp.router(routerConfig: router),
    );
  }

  testWidgets('对象详情底栏不高亮任一 tab，点第二项回到 /video-book 根目的地', (tester) async {
    final router = buildRouter();
    await tester.pumpWidget(buildApp(router));
    await tester.pumpAndSettle();

    expect(router.state.uri.path, detailLocation);
    expect(find.text('OBJECT_DETAIL'), findsOneWidget);

    final bottomNav = tester.widget<BottomNavigationWidget>(
      find.byType(BottomNavigationWidget),
    );
    expect(
      bottomNav.currentIndex,
      MainTabDestinationX.bottomNavOrdered.length,
      reason: '详情页不归属任何根 tab，底栏不得高亮任一项。',
    );
    expect(
      MainTabDestinationX.bottomNavOrdered[1],
      MainTabDestination.videoBook,
      reason: '底栏第 2 项固定为视频书。',
    );

    await tester.tap(find.byKey(TestKeys.mainTabVideoBook));
    await tester.pumpAndSettle();

    expect(router.state.uri.path, AppRoutePaths.videoBook);
    expect(find.text('VIDEO_BOOK_ROOT'), findsOneWidget);
    expect(
      find.text('OBJECT_DETAIL'),
      findsNothing,
      reason: '回根目的地应替换栈顶而不是在详情页之上叠一层。',
    );
    expect(
      router.canPop(),
      isFalse,
      reason: '`context.go` 到根目的地后不应残留可 pop 的详情页。',
    );
  });
}

final class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}
