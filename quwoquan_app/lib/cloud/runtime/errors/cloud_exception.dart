import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum CloudErrorType {
  timeout,
  network,
  unauthorized,
  forbidden,
  notFound,
  invalidResponse,
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
    this.runtimeFailure,
    this.userMessage,
    this.cause,
  });

  final CloudErrorType type;
  final String message;
  final int? statusCode;

  /// Raw error code string from the server response (e.g. "CONTENT.USER.post_not_found").
  final String? code;

  /// 全域 typed error code，来自生成的 *ErrorCode enum registry。
  final DomainErrorCode? domainErrorCode;

  /// 兼容存量 content 调用点；新代码使用 [domainErrorCode]。
  ContentErrorCode? get errorCode {
    final value = domainErrorCode?.value;
    return value is ContentErrorCode ? value : null;
  }

  final RuntimeFailureBase? runtimeFailure;

  /// User-facing message returned by a structured runtime error response.
  /// Prefer this over generic fallback text when present.
  final String? userMessage;

  final Object? cause;

  @override
  String toString() {
    return 'CloudException(type: $type, message: $message, statusCode: $statusCode, code: $code)';
  }
}
