/// 证明横切观测端口已经是**可注入**的，而不是只在物理上收敛。
///
/// 反模式基线：`AppLogService.instance` / `AppExceptionTelemetryService.instance`
/// 被业务对象直调，导致「有上报代码但无法在测试里替换」——异常是否上报、上报了什么
/// 恢复语义都不可断言。本套件锁死改造后的三条不变量：
///
/// 1. production 默认装配仍然是真实实现（没有偷偷换成 Noop/Mock）。
/// 2. 两个端口都能被 `ProviderScope` override 成测试树内的对象级 typed double。
/// 3. 真实业务对象（`ChatSendOutbox`）走的是注入进来的端口，不是单例。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../support/runtime/cloud_boundary_test_scope.dart';

/// 被记录的一次异常上报，只保留断言需要的字段。
final class _RecordedException {
  const _RecordedException({
    required this.source,
    required this.operationId,
    required this.surfaceId,
    this.error,
    this.exceptionText,
    this.runtimeFailure,
  });

  final String source;
  final String operationId;
  final String surfaceId;
  final Object? error;
  final String? exceptionText;
  final RuntimeFailureBase? runtimeFailure;
}

/// 对象级最小 typed double：只记录调用，不造业务数据、不做聚合。
final class _RecordingExceptionTelemetryPort implements ExceptionTelemetryPort {
  final List<_RecordedException> recorded = <_RecordedException>[];
  int flushCount = 0;

  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {
    recorded.add(
      _RecordedException(
        source: source,
        operationId: operationId,
        surfaceId: surfaceId,
        exceptionText: exceptionText,
        runtimeFailure: runtimeFailure,
      ),
    );
  }

  @override
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) async {
    recorded.add(
      _RecordedException(
        source: source,
        operationId: operationId,
        surfaceId: surfaceId,
        error: error,
      ),
    );
  }

  @override
  Future<void> flushPending() async => flushCount++;
}

final class _RecordingAppEventLogPort implements AppEventLogPort {
  final List<AppLogType> writtenTypes = <AppLogType>[];
  final List<Map<String, dynamic>> writtenPayloads = <Map<String, dynamic>>[];

  @override
  Future<String?> writeEvent({
    required AppLogType logType,
    required AppLogLevel level,
    required Map<String, dynamic> payload,
    required AppLogContext context,
    bool hasError = false,
    Map<String, dynamic>? summaryPayload,
  }) async {
    writtenTypes.add(logType);
    writtenPayloads.add(payload);
    return null;
  }

  @override
  Future<String?> writeRunFile({
    required String runId,
    required Map<String, dynamic> payload,
  }) async => null;
}

List<Override> _boundaryOverrides({
  ExceptionTelemetryPort? telemetry,
  AppEventLogPort? eventLog,
}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    if (telemetry != null)
      exceptionTelemetryPortProvider.overrideWithValue(telemetry),
    if (eventLog != null) appEventLogPortProvider.overrideWithValue(eventLog),
  ];
}

void main() {
  group('横切观测端口的 production 默认装配', () {
    test('exceptionTelemetryPortProvider 默认解析到真实实现', () {
      final container = ProviderContainer(overrides: _boundaryOverrides());
      addTearDown(container.dispose);

      expect(
        container.read(exceptionTelemetryPortProvider),
        isA<AppExceptionTelemetryService>(),
      );
    });

    test('appEventLogPortProvider 默认解析到真实实现', () {
      final container = ProviderContainer(overrides: _boundaryOverrides());
      addTearDown(container.dispose);

      expect(container.read(appEventLogPortProvider), isA<AppLogService>());
    });

    test('默认装配不会退化成 Noop/Mock 替身', () {
      final container = ProviderContainer(overrides: _boundaryOverrides());
      addTearDown(container.dispose);

      final telemetryType = container
          .read(exceptionTelemetryPortProvider)
          .runtimeType
          .toString();
      final logType = container.read(appEventLogPortProvider).runtimeType
          .toString();
      for (final name in <String>[telemetryType, logType]) {
        expect(
          name.toLowerCase(),
          allOf(
            isNot(contains('mock')),
            isNot(contains('noop')),
            isNot(contains('stub')),
            isNot(contains('unavailable')),
          ),
          reason: '$name 不得作为 production 默认装配',
        );
      }
    });
  });

  group('横切观测端口可被 override 替换', () {
    test('异常端口 override 后由测试 double 接收上报', () async {
      final telemetry = _RecordingExceptionTelemetryPort();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(telemetry: telemetry),
      );
      addTearDown(container.dispose);

      expect(container.read(exceptionTelemetryPortProvider), same(telemetry));

      await container.read(exceptionTelemetryPortProvider).recordHandledException(
        source: 'runtime.observability.port_contract',
        error: StateError('injected_failure'),
        stackTrace: StackTrace.current,
        operationId: 'app.runtime.capture_exception',
      );

      expect(telemetry.recorded, hasLength(1));
      expect(telemetry.recorded.single.source, 'runtime.observability.port_contract');
      expect(telemetry.recorded.single.error, isA<StateError>());
    });

    test('日志端口 override 后由测试 double 接收事件', () async {
      final eventLog = _RecordingAppEventLogPort();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(eventLog: eventLog),
      );
      addTearDown(container.dispose);

      await container.read(appEventLogPortProvider).writeEvent(
        logType: AppLogType.pageAccess,
        level: AppLogLevel.info,
        payload: <String, dynamic>{'event': 'open'},
        context: const AppLogContext(),
      );

      expect(eventLog.writtenTypes, <AppLogType>[AppLogType.pageAccess]);
      expect(eventLog.writtenPayloads.single['event'], 'open');
    });

    test('flushPending 也走注入端口', () async {
      final telemetry = _RecordingExceptionTelemetryPort();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(telemetry: telemetry),
      );
      addTearDown(container.dispose);

      await container.read(exceptionTelemetryPortProvider).flushPending();

      expect(telemetry.flushCount, 1);
    });
  });

  group('业务对象消费注入端口而不是单例', () {
    test('ChatSendOutbox 的异常端口只能由构造方注入', () {
      final telemetry = _RecordingExceptionTelemetryPort();
      final outbox = ChatSendOutbox(
        maxQueueSize: 8,
        sendCommand: (_) async {},
        sendQueuedVoice: (_, _) async => throw UnimplementedError(),
        telemetry: telemetry,
      );

      // `telemetry` 是 required 具名参数：没有单例默认值可回退，
      // 因此「outbox 只会报给注入进来的端口」是类型层面的结构保证。
      expect(outbox.telemetry, same(telemetry));
    });

    testWidgets('BuildContext-only 调用点经 ProviderScope 解析到 override 端口', (
      tester,
    ) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      ExceptionTelemetryPort? resolvedFromContext;

      await tester.pumpWidget(
        ProviderScope(
          overrides: _boundaryOverrides(telemetry: telemetry),
          child: Builder(
            builder: (context) {
              // 这正是 content_share_actions / assistant_half_sheet 这类
              // 只拿到 BuildContext 的静态入口所走的解析路径。
              resolvedFromContext = ProviderScope.containerOf(
                context,
              ).read(exceptionTelemetryPortProvider);
              return const SizedBox.shrink();
            },
          ),
        ),
      );

      expect(resolvedFromContext, same(telemetry));
    });
  });
}
