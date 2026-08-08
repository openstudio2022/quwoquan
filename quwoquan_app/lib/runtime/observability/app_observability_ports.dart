import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 异常遥测的注入边界。
///
/// 业务对象（`lib/service/**`）只依赖本接口，由
/// `exceptionTelemetryPortProvider` 在 composition root 绑定实现；
/// local_contract 通过 provider override 换成测试树内的对象级 typed double，
/// 从而让「异常是否上报、上报了什么语义」成为可断言行为而不是隐式单例副作用。
abstract interface class ExceptionTelemetryPort {
  /// 未捕获或已在调用点降级的异常入口：只接受已经字符串化的异常与栈。
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId,
    String pageName,
    String surfaceId,
    String routeId,
    String operationId,
    RuntimeFailureBase? runtimeFailure,
    String exceptionType,
  });

  /// 已捕获并已降级处理的异常入口：由实现负责经 `CloudErrorMapper`
  /// 派生 code/kind/reason，调用点不得自行拼装错误语义。
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId,
    String pageName,
    String surfaceId,
    String routeId,
    String operationId,
  });

  Future<void> flushPending();
}

/// 结构化事件日志的注入边界。
abstract interface class AppEventLogPort {
  Future<String?> writeEvent({
    required AppLogType logType,
    required AppLogLevel level,
    required Map<String, dynamic> payload,
    required AppLogContext context,
    bool hasError,
    Map<String, dynamic>? summaryPayload,
  });

  Future<String?> writeRunFile({
    required String runId,
    required Map<String, dynamic> payload,
  });
}
