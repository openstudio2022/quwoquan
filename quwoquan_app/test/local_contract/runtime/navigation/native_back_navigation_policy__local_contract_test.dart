// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/global-route-edge-pop-contract/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/home-edge-swipe-exit-guard/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/home-edge-swipe-exit-guard/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/home-edge-swipe-exit-guard/spec.md#gwt-001.t2

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/native_back_navigation.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

void main() {
  group('NativeBackNavigationPolicy', () {
    test('iOS uses leading edge and does not guard root exit', () {
      final policy = nativeBackNavigationPolicyForPlatform(TargetPlatform.iOS);

      expect(policy, isA<IosNativeBackNavigationPolicy>());
      expect(policy.supportedBackEdges, {EdgeBackDirection.leading});
      expect(
        policy.resolveBack(
          const AppRouteContext(
            location: AppRoutePaths.home,
            canPop: false,
            isBottomNavRoot: true,
          ),
        ),
        AppBackDisposition.ignoreRoot,
      );
    });

    test('Android supports both edges and guards bottom-nav root exit', () {
      final policy = nativeBackNavigationPolicyForPlatform(
        TargetPlatform.android,
      );

      expect(policy, isA<AndroidNativeBackNavigationPolicy>());
      expect(policy.supportedBackEdges, {
        EdgeBackDirection.leading,
        EdgeBackDirection.trailing,
      });
      expect(
        policy.resolveBack(
          const AppRouteContext(
            location: AppRoutePaths.home,
            canPop: false,
            isBottomNavRoot: true,
          ),
        ),
        AppBackDisposition.guardRootExit,
      );
    });

    test('non-root routes prefer Router pop before root exit guard', () {
      final policy = nativeBackNavigationPolicyForPlatform(
        TargetPlatform.android,
      );

      expect(
        policy.resolveBack(
          const AppRouteContext(
            location: '/works/browser?workId=1',
            canPop: true,
            isBottomNavRoot: false,
          ),
        ),
        AppBackDisposition.popRoute,
      );
    });

    test('platform page factory maps ordinary pages to native page types', () {
      const key = ValueKey<String>('native-page');
      const child = SizedBox.shrink();
      const spec = AppRoutePageSpec<void>(key: key, child: child);

      expect(
        const IosNativeBackNavigationPolicy().buildPage<void>(spec),
        isA<CupertinoPage<void>>(),
      );
      expect(
        const AndroidNativeBackNavigationPolicy().buildPage<void>(spec),
        isA<MaterialPage<void>>(),
      );
    });
  });

  testWidgets('Android 根页首次返回只提示，保护窗口内第二次才请求退出', (tester) async {
    var exitRequestCount = 0;
    late final GoRouter router;
    router = GoRouter(
      initialLocation: AppRoutePaths.home,
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (context, _) => AppNativeBackScope(
            router: GoRouter.of(context),
            policy: const AndroidNativeBackNavigationPolicy(),
            onExitRequested: () async => exitRequestCount += 1,
            child: const SizedBox.shrink(),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();

    await tester.binding.handlePopRoute();
    await tester.pump();

    expect(exitRequestCount, 0);
    expect(find.text(FoundationText.edgeBackExitPrompt), findsOneWidget);

    await tester.binding.handlePopRoute();
    await tester.pump();

    expect(exitRequestCount, 1);
    await tester.pump(const Duration(seconds: 2));
  });

  testWidgets('非根路由返回交还 Router 并回到上一页', (tester) async {
    const detailPath = '/native-back-detail';
    late final GoRouter router;
    router = GoRouter(
      initialLocation: AppRoutePaths.home,
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (context, _) => AppNativeBackScope(
            router: GoRouter.of(context),
            policy: const AndroidNativeBackNavigationPolicy(),
            child: const Text('home-route'),
          ),
        ),
        GoRoute(
          path: detailPath,
          builder: (context, _) => AppNativeBackScope(
            router: GoRouter.of(context),
            policy: const AndroidNativeBackNavigationPolicy(),
            child: const Text('detail-route'),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
    router.push(detailPath);
    await tester.pumpAndSettle();
    expect(find.text('detail-route'), findsOneWidget);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(find.text('home-route'), findsOneWidget);
    expect(find.text('detail-route'), findsNothing);
  });
}
