import 'package:quwoquan_runtime_errors/src/runtime_failure.dart';

class RuntimeErrorResponse {
  const RuntimeErrorResponse({
    required this.failure,
    this.requestId = '',
    this.traceId = '',
    this.userMessage = '',
    this.debugMessage = '',
  });

  factory RuntimeErrorResponse.fromJson(
    Map<String, dynamic> json, {
    int? transportStatus,
  }) {
    final failureJson = <String, dynamic>{
      'code': json['code'],
      'semanticReason': json['reason'],
      'transportStatus': transportStatus ?? json['transportStatus'],
      'origin': json['origin'],
      'kind': _camelKind(json['kind']),
      'nature': json['nature'],
      'location': json['location'],
      'context': json['context'],
      'recovery': json['recovery'],
    };
    return RuntimeErrorResponse(
      failure: RuntimeFailure.fromJson(failureJson),
      requestId: (json['requestId'] as String?) ?? '',
      traceId: (json['traceId'] as String?) ?? '',
      userMessage: (json['userMessage'] as String?) ?? '',
      debugMessage: (json['debugMessage'] as String?) ?? '',
    );
  }

  final RuntimeFailure failure;
  final String requestId;
  final String traceId;
  final String userMessage;
  final String debugMessage;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'code': failure.code,
      'reason': failure.semanticReason,
      if (failure.transportStatus != null)
        'transportStatus': failure.transportStatus,
      'origin': failure.origin.name,
      'kind': failure.kind.name,
      'nature': failure.nature.name,
      'requestId': requestId,
      'traceId': traceId,
      'userMessage': userMessage,
      'debugMessage': debugMessage,
      'location': failure.location.toJson(),
      'context': failure.context.toJson(),
      'recovery': failure.recovery.toJson(),
    };
  }
}

Object? _camelKind(Object? raw) {
  if (raw is! String) return raw;
  switch (raw) {
    case 'rate_limited':
    case 'RATE_LIMITED':
      return 'rateLimited';
    case 'not_found':
    case 'NOT_FOUND':
      return 'notFound';
  }
  return raw;
}
