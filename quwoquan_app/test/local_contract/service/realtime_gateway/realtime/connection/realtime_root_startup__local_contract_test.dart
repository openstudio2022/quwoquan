import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/composition/quwoquan_app_shell.dart';

void main() {
  test('startup init foregrounds realtime without background side effects', () {
    final calls = <String>[];

    handleQuwoquanAppLifecycleState(
      state: AppLifecycleState.resumed,
      refreshAppearance: () => calls.add('refresh'),
      onRealtimeForeground: () => calls.add('foreground'),
      onRealtimeBackground: () => calls.add('background'),
    );

    expect(calls, <String>['refresh', 'foreground']);
  });
}
