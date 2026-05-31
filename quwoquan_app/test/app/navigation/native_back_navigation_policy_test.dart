import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/native_back_navigation.dart';

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
            location: '/article/1',
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
}
