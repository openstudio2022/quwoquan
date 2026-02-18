class AssistentApiEnvelope<T> {
  const AssistentApiEnvelope({
    required this.success,
    required this.runId,
    required this.traceId,
    required this.degraded,
    this.errorCode,
    this.message,
    this.data,
  });

  final bool success;
  final String runId;
  final String traceId;
  final bool degraded;
  final String? errorCode;
  final String? message;
  final T? data;

  Map<String, dynamic> toJson(Map<String, dynamic> Function(T value)? encode) {
    return <String, dynamic>{
      'success': success,
      'runId': runId,
      'traceId': traceId,
      'degraded': degraded,
      'errorCode': errorCode,
      'message': message,
      'data': data == null || encode == null ? data : encode(data as T),
    };
  }
}

class AssistentApiError {
  const AssistentApiError({
    required this.code,
    required this.message,
    required this.statusCode,
  });

  final String code;
  final String message;
  final int statusCode;
}

