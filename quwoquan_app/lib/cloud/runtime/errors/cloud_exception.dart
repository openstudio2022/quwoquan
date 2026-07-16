import 'package:quwoquan_app/cloud/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum CloudErrorType {
  timeout,
  cancelled,
  network,
  unauthorized,
  forbidden,
  notFound,
  invalidResponse,
  rateLimited,
  server,
  unknown,
}

class CloudException implements Exception {
  CloudException({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
    this.domainErrorCode,
    required this.runtimeFailure,
    this.userMessage,
    this.requestId,
    this.traceId,
    this.retryAfter,
    this.cause,
  });

  final CloudErrorType type;
  final String message;
  final int? statusCode;

  /// Raw error code string from the server response (e.g. "CONTENT.USER.post_not_found").
  final String? code;

  /// 全域 typed error code，来自生成的 *ErrorCode enum registry。
  final DomainErrorCode? domainErrorCode;

  final RuntimeFailureBase runtimeFailure;

  /// User-facing message returned by a structured runtime error response.
  /// Prefer this over generic fallback text when present.
  final String? userMessage;

  /// Correlation identifiers returned by RuntimeErrorResponse.
  final String? requestId;
  final String? traceId;
  final Duration? retryAfter;

  final Object? cause;

  @override
  String toString() {
    return 'CloudException(type: $type, message: $message, statusCode: $statusCode, code: $code, requestId: $requestId, traceId: $traceId)';
  }
}
