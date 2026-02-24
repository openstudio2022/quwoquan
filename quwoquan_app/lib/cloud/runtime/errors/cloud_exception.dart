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
    this.cause,
  });

  final CloudErrorType type;
  final String message;
  final int? statusCode;
  final String? code;
  final Object? cause;

  @override
  String toString() {
    return 'CloudException(type: $type, message: $message, statusCode: $statusCode, code: $code)';
  }
}
