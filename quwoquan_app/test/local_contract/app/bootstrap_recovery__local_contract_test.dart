import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/bootstrap_recovery.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_event_record_errors.g.dart';

void main() {
  test('runApp 前配置失败转换为 metadata 驱动的可重试恢复语义', () {
    final failure = BootstrapFailure.fromError(
      StateError('missing required endpoint'),
    );

    expect(
      failure.errorCode,
      OpsEventRecordErrorCode.startupConfigurationInvalid,
    );
    expect(failure.runtimeFailure.recovery.action, 'retry');
  });

  testWidgets('恢复根不依赖 Router 或远端 Provider 即可展示重试', (tester) async {
    var retryCalls = 0;
    await tester.pumpWidget(
      BootstrapRecoveryApp(
        failure: BootstrapFailure.fromError(
          StateError('missing required endpoint'),
        ),
        onRetry: () async {
          retryCalls++;
        },
      ),
    );

    expect(find.text('重新尝试'), findsOneWidget);
    await tester.tap(find.text('重新尝试'));
    await tester.pump();
    expect(retryCalls, 1);
  });

  test('首帧前 Flutter、Platform 和 root isolate 错误都会调度恢复根', () {
    final source = File('lib/app_bootstrap.dart').readAsStringSync();

    expect(source, contains('_scheduleBootstrapRecoveryBeforeFirstFrame('));
    final flutterHandler = source.indexOf('FlutterError.onError =');
    final platformHandler = source.indexOf(
      'PlatformDispatcher.instance.onError',
    );
    expect(
      source.indexOf(
        '_scheduleBootstrapRecoveryBeforeFirstFrame(',
        flutterHandler,
      ),
      greaterThan(flutterHandler),
    );
    expect(
      source.indexOf(
        '_scheduleBootstrapRecoveryBeforeFirstFrame(',
        platformHandler,
      ),
      greaterThan(platformHandler),
    );
    expect(source, contains("source: 'root_isolate'"));
    final recoveryRoot = source.indexOf('BootstrapRecoveryApp(');
    expect(
      source.indexOf(
        'AppStartupRuntime.instance.markFirstFramePainted();',
        recoveryRoot,
      ),
      greaterThan(recoveryRoot),
      reason: '恢复根本身也必须确认 Flutter 首帧，避免 native watchdog 覆盖可操作恢复 UI',
    );
  });
}
