import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
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
    this.errorCode,
    this.runtimeFailure,
    this.cause,
  });

  final CloudErrorType type;
  final String message;
  final int? statusCode;

  /// Raw error code string from the server response (e.g. "CONTENT.USER.post_not_found").
  final String? code;

  /// Typed [ContentErrorCode] parsed from [code]. Null when not a content-domain error.
  final ContentErrorCode? errorCode;

  final RuntimeFailureBase? runtimeFailure;

  final Object? cause;

  @override
  String toString() {
    return 'CloudException(type: $type, message: $message, statusCode: $statusCode, code: $code)';
  }
}
