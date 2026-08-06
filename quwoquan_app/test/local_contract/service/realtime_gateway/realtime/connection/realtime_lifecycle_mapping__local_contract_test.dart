import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/shell/composition/quwoquan_app_shell.dart';

void main() {
  test('resumed refreshes appearance and foregrounds realtime', () {
    final calls = <String>[];

    handleQuwoquanAppLifecycleState(
      state: AppLifecycleState.resumed,
      refreshAppearance: () => calls.add('refresh'),
      onRealtimeForeground: () => calls.add('foreground'),
      onRealtimeBackground: () => calls.add('background'),
    );

    expect(calls, <String>['refresh', 'foreground']);
  });

  test('hidden sends realtime to background without refreshing appearance', () {
    final calls = <String>[];

    handleQuwoquanAppLifecycleState(
      state: AppLifecycleState.hidden,
      refreshAppearance: () => calls.add('refresh'),
      onRealtimeForeground: () => calls.add('foreground'),
      onRealtimeBackground: () => calls.add('background'),
    );

    expect(calls, <String>['background']);
  });

  test('inactive does not mutate lifecycle side effects', () {
    final calls = <String>[];

    handleQuwoquanAppLifecycleState(
      state: AppLifecycleState.inactive,
      refreshAppearance: () => calls.add('refresh'),
      onRealtimeForeground: () => calls.add('foreground'),
      onRealtimeBackground: () => calls.add('background'),
    );

    expect(calls, isEmpty);
  });
}
