import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/recovery/bootstrap_recovery.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';

void main() {
  test('runApp 前配置失败转换为 metadata 驱动的外部恢复语义', () {
    final failure = BootstrapFailure.fromError(
      CloudRuntimeConfigurationException(
        runtimeEnv: '',
        invalidKeys: const <String>[
          'APP_RUNTIME_ENV',
          'CLOUD_GATEWAY_BASE_URL',
        ],
      ),
    );

    expect(
      failure.errorCode,
      OpsEventRecordErrorCode.startupConfigurationInvalid,
    );
    expect(failure.runtimeFailure.recovery.action, 'externalRecovery');
    expect(
      failure.runtimeFailure.context.attributes.map(
        (attribute) => attribute.value,
      ),
      contains('APP_RUNTIME_ENV,CLOUD_GATEWAY_BASE_URL'),
    );
  });

  test('普通 StateError 不得伪装成启动配置错误', () {
    final failure = BootstrapFailure.fromError(
      StateError('router state failed'),
    );

    expect(
      failure.errorCode,
      OpsEventRecordErrorCode.startupInitializationFailed,
    );
  });

  testWidgets('恢复根不依赖 Router 或远端 Provider 即可展示网页版安全出口', (tester) async {
    await tester.pumpWidget(
      BootstrapRecoveryApp(
        failure: BootstrapFailure.fromError(
          CloudRuntimeConfigurationException(
            runtimeEnv: '',
            invalidKeys: const <String>['CLOUD_GATEWAY_BASE_URL'],
          ),
        ),
      ),
    );

    await tester.pump();
    expect(find.text('使用网页版'), findsOneWidget);
    expect(find.text('重新尝试'), findsNothing);
  });

  test('首帧前 Flutter、Platform 和 root isolate 错误都会调度恢复根', () {
    final source = File('lib/runtime/shell/startup/app_bootstrap.dart').readAsStringSync();

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

  test('未捕获异常只允许单写：diagnostics 接管后 bootstrap 记录必须让位', () {
    final bootstrap = File(
      'lib/runtime/shell/startup/app_bootstrap.dart',
    ).readAsStringSync();
    final diagnostics = File(
      'lib/runtime/observability/runtime_diagnostics.dart',
    ).readAsStringSync();

    // diagnostics 在 install/dispose 时维护接管标志。
    expect(diagnostics, contains('globalUncaughtCaptureActive = true'));
    expect(diagnostics, contains('globalUncaughtCaptureActive = false'));

    // bootstrap 的 flutter_error 与 platform_dispatcher 记录点都必须被
    // 接管标志守卫，否则同一未捕获异常会写出两条不同指纹的 ES 记录。
    for (final source in <String>[
      "source: 'flutter_error'",
      "source: 'platform_dispatcher'",
    ]) {
      final recordIndex = bootstrap.indexOf(source);
      expect(recordIndex, greaterThan(0));
      final guardIndex = bootstrap.lastIndexOf(
        '!AppRuntimeDiagnostics.globalUncaughtCaptureActive',
        recordIndex,
      );
      expect(
        guardIndex,
        greaterThan(0),
        reason: 'bootstrap 的 $source 记录点缺少 diagnostics 接管让位守卫',
      );
    }

    // zone / root isolate / bootstrap 失败路径不经过 diagnostics 链，
    // 必须保留 bootstrap 记录（不受让位守卫影响）。
    expect(bootstrap, contains("source: 'zone_guarded'"));
    expect(bootstrap, contains("source: 'root_isolate'"));
  });

  test('重试复用首次 bootstrap Zone，避免 Zone mismatch', () {
    final source = File('lib/runtime/shell/startup/app_bootstrap.dart').readAsStringSync();

    expect(source, contains('Zone? _bootstrapZone'));
    expect(source, contains('_bootstrapZone = Zone.current'));
    expect(source, contains('_runQuwoquanAppInBootstrapZone'));
    expect(source, contains('existingZone.run('));
    expect(
      source,
      contains('zone.scheduleMicrotask('),
      reason: '首帧前恢复调度也必须回到 bootstrap Zone',
    );
    expect(
      'runZonedGuarded('.allMatches(source).length,
      1,
      reason: '整个 isolate 生命周期只允许创建一次 bootstrap Zone',
    );
  });
}
