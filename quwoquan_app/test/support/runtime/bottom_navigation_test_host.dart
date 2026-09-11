import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';

import 'cloud_boundary_test_scope.dart';

/// 仅隔离导航所需登录与主题状态，不装配内容、网络或播放器。
Widget bottomNavigationTestHost({
  required Widget child,
  Brightness brightness = Brightness.light,
  double textScale = 1,
}) {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      authSessionControllerProvider.overrideWith(_GuestSession.new),
      isDarkProvider.overrideWithValue(brightness == Brightness.dark),
    ],
    child: CupertinoApp(
      theme: CupertinoThemeData(brightness: brightness),
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: CupertinoPageScaffold(child: child),
        ),
      ),
    ),
  );
}

Widget bottomNavigationUnderTest({
  int currentIndex = 0,
  ValueChanged<int>? onTap,
}) => Align(
  alignment: Alignment.bottomCenter,
  child: BottomNavigationWidget(
    currentIndex: currentIndex,
    onTap: onTap ?? (_) {},
  ),
);

final class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}
