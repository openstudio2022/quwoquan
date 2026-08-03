import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Android startup watchdog contract', () {
    test('renderer 首帧会取消性能 watchdog，恢复 gate 不进入 Flutter Activity', () {
      final activity = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
      );
      final confirmation = _section(
        activity,
        'private void confirmFlutterFirstFrame',
        'private void confirmStartupSafeTerminal',
      );

      expect(confirmation, contains('cancelFlutterFirstFrameWatchdog();'));
      expect(
        confirmation,
        isNot(
          contains('dismissNativeStartupRecoveryAfterFlutterFirstFrame();'),
        ),
      );
      expect(
        activity,
        isNot(contains('android_startup_safe_terminal_timeout')),
      );
      expect(activity, isNot(contains('showNativeStartupRecovery')));
    });

    test('deadline 仅记录首帧性能超时，不把等待超时判为致命异常', () {
      final activity = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
      );
      final deadline = _section(
        activity,
        'private synchronized void triggerNativeFirstFrameDeadline',
        'private void recordNativeStartupDeadline',
      );

      expect(deadline, contains('flutterFirstFrameConfirmed'));
      expect(
        deadline,
        isNot(contains('showNativeStartupRecovery(elapsedMs, false);')),
      );
      expect(
        deadline,
        contains('recordNativeStartupDeadline(elapsedMs, true);'),
      );
      expect(
        _section(
          activity,
          'private void recordNativeStartupDeadline',
          'private String startupAttemptLogSuffix',
        ),
        contains('if (!firstFrameMissing)'),
      );
    });

    test('safe terminal 后才注册启动后插件，启动恢复不提供重试', () {
      final scheduler = _readAppFile('lib/app/startup_init_scheduler.dart');
      final shell = _readAppFile('lib/quwoquan_app_shell.dart');
      final activity = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
      );

      final firstFrame = _section(
        scheduler,
        'void onFirstFrame',
        '/// 欢迎页首帧可见后启动',
      );
      expect(firstFrame, isNot(contains('_startPostFirstFrameTasks();')));
      expect(scheduler, contains('void onSafeTerminal()'));
      expect(shell, contains('_startupInitScheduler.onSafeTerminal();'));

      expect(
        activity,
        isNot(contains('private void requestNewStartupAttempt()')),
      );
      expect(activity, isNot(contains('startActivity(launchIntent);')));
      expect(activity, isNot(contains('recreate();')));
    });

    test('native timing hydration 只向前收紧并重新 arm Flutter deadline', () {
      final runtime = _readAppFile('lib/app/app_startup_runtime.dart');
      final shell = _readAppFile('lib/quwoquan_app_shell.dart');
      final welcome = _readAppFile('lib/ui/welcome/pages/welcome_screen.dart');

      expect(runtime, contains('deadlineElapsedSinceProcessStart'));
      expect(runtime, contains("_attemptKind == 'hotRestart'"));
      expect(runtime, contains('nativeDeadline > deadlineBeforeHydration'));
      expect(shell, contains('_hydrateNativeTimingForTelemetry'));
      expect(shell, contains('_armStartupDeadline();'));
      expect(
        welcome,
        contains('AppStartupRuntime.instance.deadlineElapsedSinceProcessStart'),
      );
      expect(welcome, contains('_armDeadline();'));
      expect(
        _section(
          shell,
          'void _armStartupDeadline',
          'Future<void> _hydrateNativeTimingForTelemetry',
        ),
        isNot(contains('forceSafeRecovery')),
      );
    });
  });
}

String _section(String source, String start, String end) {
  final startIndex = source.indexOf(start);
  final endIndex = source.indexOf(end, startIndex);
  expect(startIndex, greaterThanOrEqualTo(0), reason: start);
  expect(endIndex, greaterThan(startIndex), reason: end);
  return source.substring(startIndex, endIndex);
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
