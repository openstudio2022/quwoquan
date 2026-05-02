import 'package:quwoquan_runtime_errors/src/runtime_failure.dart';
import 'package:quwoquan_runtime_errors/src/runtime_failure_context.dart';
import 'package:quwoquan_runtime_errors/src/runtime_failure_location.dart';

class RuntimeErrorResponse {
  const RuntimeErrorResponse({
    required this.failure,
    this.requestId = '',
    this.traceId = '',
    this.userMessage = '',
    this.debugMessage = '',
  });

  factory RuntimeErrorResponse.fromJson(Map<String, dynamic> json) {
    final failureJson = <String, dynamic>{
      'code': json['code'],
      'origin': json['origin'],
      'kind': _camelKind(json['kind']),
      'nature': json['nature'],
      'location': json['location'],
      'context': json['context'],
    };
    return RuntimeErrorResponse(
      failure: RuntimeFailure.fromJson(failureJson),
      requestId: (json['requestId'] as String?) ?? '',
      traceId: (json['traceId'] as String?) ?? '',
      userMessage: (json['userMessage'] as String?) ?? '',
      debugMessage: (json['debugMessage'] as String?) ?? '',
    );
  }

  factory RuntimeErrorResponse.fromCurrentJson(Map<String, dynamic> json) {
    final code = (json['code'] as String?) ?? 'CLOUD.SYSTEM.unknown_error';
    return RuntimeErrorResponse(
      failure: RuntimeFailure(
        code: code,
        origin: _originFromCurrentKind(json['kind']),
        kind: _failureKindFromCode(code),
        nature: _natureFromKind(json['kind']),
        location: const RuntimeFailureLocation(
          businessObject: 'cloud_request',
          functionModule: 'cloud_error_mapper',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            if (json['module'] != null)
              RuntimeContextAttribute(
                key: 'module',
                value: json['module'].toString(),
              ),
            if (json['reason'] != null)
              RuntimeContextAttribute(
                key: 'reason',
                value: json['reason'].toString(),
              ),
          ],
        ),
      ),
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
      'origin': failure.origin.name,
      'kind': failure.kind.name,
      'nature': failure.nature.name,
      'requestId': requestId,
      'traceId': traceId,
      'userMessage': userMessage,
      'debugMessage': debugMessage,
      'location': failure.location.toJson(),
      'context': failure.context.toJson(),
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

RuntimeFailureOrigin _originFromCurrentKind(Object? raw) {
  switch ((raw as String?)?.toUpperCase()) {
    case 'USER':
      return RuntimeFailureOrigin.user;
    case 'NETWORK':
      return RuntimeFailureOrigin.environment;
    case 'MIDDLEWARE':
      return RuntimeFailureOrigin.remoteDependency;
    case 'SYSTEM':
      return RuntimeFailureOrigin.system;
  }
  return RuntimeFailureOrigin.system;
}

RuntimeFailureNature _natureFromKind(Object? raw) {
  switch ((raw as String?)?.toUpperCase()) {
    case 'USER':
      return RuntimeFailureNature.requiresUserAction;
    case 'NETWORK':
    case 'MIDDLEWARE':
      return RuntimeFailureNature.transient;
  }
  return RuntimeFailureNature.bug;
}

RuntimeFailureKind _failureKindFromCode(String code) {
  final lower = code.toLowerCase();
  if (lower.contains('timeout')) return RuntimeFailureKind.timeout;
  if (lower.contains('permission')) return RuntimeFailureKind.permission;
  if (lower.contains('unauthorized')) return RuntimeFailureKind.auth;
  if (lower.contains('not_found')) return RuntimeFailureKind.notFound;
  if (lower.contains('parse')) return RuntimeFailureKind.parsing;
  if (lower.contains('contract')) return RuntimeFailureKind.contract;
  if (lower.contains('unavailable')) return RuntimeFailureKind.unavailable;
  return RuntimeFailureKind.internal;
}
