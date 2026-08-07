import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_log_policy.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_app/runtime/observability/app_log_writer.dart';
import 'package:quwoquan_app/runtime/observability/operation_privacy_redactor.dart';

class _MemoryAppLogWriter extends AppLogWriter {
  String? lastLine;

  @override
  Future<String> appendLogLine({
    required String subDirectory,
    required String fileName,
    required String line,
    DateTime? at,
  }) async {
    lastLine = line;
    return 'memory://$subDirectory/$fileName';
  }
}

/// 证明 `operation.privacy` 在真实端侧日志出口生效，而不只是 redactor 单测通过。
///
/// 这里断言的是落盘那一行文本：只要高敏原值出现在 `writer.lastLine` 里，就是真实
/// 泄漏，无论中间层做了什么。
void main() {
  AppLogService buildService(_MemoryAppLogWriter writer) =>
      AppLogService.forTesting(
        writer: writer,
        policy: AppLogPolicy(isRelease: false),
      );

  test('pii 请求载荷的原值不会出现在落盘日志行里', () async {
    final writer = _MemoryAppLogWriter();

    await buildService(writer).writeEvent(
      logType: AppLogType.cloudApi,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{
        'msg': 'reserve original image access',
        'requesterUserId': 'user_10086',
        'purpose': 'download',
      },
      context: const AppLogContext(
        requestId: 'req-privacy-1',
        operationId:
            'content.original_access_quota.ReserveOriginalImageAccessGrant',
      ),
    );

    expect(writer.lastLine, isNotNull);
    expect(writer.lastLine, isNot(contains('user_10086')));
    expect(writer.lastLine, isNot(contains('download')));
  });

  test('secret operation 的载荷完全不落盘', () async {
    final writer = _MemoryAppLogWriter();

    await buildService(writer).writeEvent(
      logType: AppLogType.cloudApi,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{
        'authorizationCode': 'ac_live_9f2c',
        'codeVerifier': 'cv_7731',
      },
      context: const AppLogContext(
        operationId:
            'integration.connector_authorization.CompleteOAuthConnectorAuthorization',
      ),
    );

    expect(writer.lastLine, isNotNull);
    expect(writer.lastLine, isNot(contains('ac_live_9f2c')));
    expect(writer.lastLine, isNot(contains('cv_7731')));
  });

  test('未登记 operation fail-closed，载荷不落盘', () async {
    final writer = _MemoryAppLogWriter();

    await buildService(writer).writeEvent(
      logType: AppLogType.cloudApi,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{'secretish': 'leak_me_please'},
      context: const AppLogContext(
        operationId: 'content.post.OperationThatDoesNotExist',
      ),
    );

    expect(writer.lastLine, isNotNull);
    expect(writer.lastLine, isNot(contains('leak_me_please')));
  });

  test('未声明 operation 的日志保持既有行为，不被误伤', () async {
    final writer = _MemoryAppLogWriter();

    await buildService(writer).writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{'msg': 'open reader page'},
      context: const AppLogContext(),
    );

    expect(writer.lastLine, contains('open reader page'));
  });

  test('response 方向独立取密级', () async {
    final writer = _MemoryAppLogWriter();

    await buildService(writer).writeEvent(
      logType: AppLogType.cloudApi,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{'msg': 'variant_treatment_b'},
      context: const AppLogContext(
        operationId: 'ops.experiment_assignment_fact.GetExperimentAssignment',
        operationDirection: OperationPayloadDirection.response,
      ),
    );

    expect(writer.lastLine, isNot(contains('variant_treatment_b')));
  });
}
