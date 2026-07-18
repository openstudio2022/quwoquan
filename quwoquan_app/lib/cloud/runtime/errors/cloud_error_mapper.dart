import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class CloudErrorMapper {
  const CloudErrorMapper._();

  static CloudException fromStatusCode(
    int statusCode, {
    String? body,
    String? requestPath,
    String? retryAfter,
  }) {
    final code = _readCode(body);
    final domainErrorCode = DomainErrorCodeRegistry.fromCode(code);
    final runtimeResponse = _readRuntimeErrorResponse(
      body,
      transportStatus: statusCode,
    );
    final runtimeFailure = runtimeFailureFromStatusCode(
      statusCode,
      body: body,
      requestPath: requestPath,
    );
    final suffix = requestPath == null ? '' : ' ($requestPath)';
    final retryDelay = _parseRetryAfter(retryAfter);
    if (statusCode == 401) {
      return CloudException(
        type: CloudErrorType.unauthorized,
        statusCode: statusCode,
        message: 'Unauthorized$suffix',
        code: code,
        domainErrorCode: domainErrorCode,
        runtimeFailure: runtimeFailure,
        userMessage: parsedUserMessage(body),
        requestId: runtimeResponse?.requestId,
        traceId: runtimeResponse?.traceId,
        retryAfter: retryDelay,
      );
    }
    if (statusCode == 403) {
      return CloudException(
        type: CloudErrorType.forbidden,
        statusCode: statusCode,
        message: 'Forbidden$suffix',
        code: code,
        domainErrorCode: domainErrorCode,
        runtimeFailure: runtimeFailure,
        userMessage: parsedUserMessage(body),
        requestId: runtimeResponse?.requestId,
        traceId: runtimeResponse?.traceId,
        retryAfter: retryDelay,
      );
    }
    if (statusCode == 404) {
      return CloudException(
        type: CloudErrorType.notFound,
        statusCode: statusCode,
        message: 'Not found$suffix',
        code: code,
        domainErrorCode: domainErrorCode,
        runtimeFailure: runtimeFailure,
        userMessage: parsedUserMessage(body),
        requestId: runtimeResponse?.requestId,
        traceId: runtimeResponse?.traceId,
        retryAfter: retryDelay,
      );
    }
    if (statusCode >= 500) {
      return CloudException(
        type: CloudErrorType.server,
        statusCode: statusCode,
        message: 'Server error$suffix',
        code: code,
        domainErrorCode: domainErrorCode,
        runtimeFailure: runtimeFailure,
        userMessage: parsedUserMessage(body),
        requestId: runtimeResponse?.requestId,
        traceId: runtimeResponse?.traceId,
        retryAfter: retryDelay,
      );
    }
    return CloudException(
      type: _cloudTypeFromFailure(runtimeFailure),
      statusCode: statusCode,
      message: 'HTTP $statusCode$suffix',
      code: code,
      domainErrorCode: domainErrorCode,
      runtimeFailure: runtimeFailure,
      userMessage: parsedUserMessage(body),
      requestId: runtimeResponse?.requestId,
      traceId: runtimeResponse?.traceId,
      retryAfter: retryDelay,
    );
  }

  static CloudException fromException(Object error, {String? requestPath}) {
    final runtimeFailure = runtimeFailureFromException(
      error,
      requestPath: requestPath,
    );
    return CloudException(
      type: _cloudTypeFromFailure(runtimeFailure),
      message: runtimeFailure.code,
      code: runtimeFailure.code,
      runtimeFailure: runtimeFailure,
      cause: error,
    );
  }

  static CloudException invalidResponse({
    required String message,
    String? requestPath,
    String functionModule = 'cloud_response_decoder',
  }) {
    final failure = RuntimeFailure(
      code: RuntimeFailureCodes.appContractInvalidResponse,
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.contract,
      nature: RuntimeFailureNature.bug,
      location: RuntimeFailureLocation(
        businessObject: 'cloud_response',
        functionModule: functionModule,
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'message', value: message),
          if (requestPath != null && requestPath.trim().isNotEmpty)
            RuntimeContextAttribute(key: 'requestPath', value: requestPath),
        ],
      ),
    );
    return CloudException(
      type: CloudErrorType.invalidResponse,
      message: message,
      code: failure.code,
      runtimeFailure: failure,
      userMessage: message,
    );
  }

  static RuntimeFailure runtimeFailureFromException(
    Object error, {
    String? requestPath,
  }) {
    if (error is CloudException) {
      final failure = error.runtimeFailure;
      if (failure is RuntimeFailure) return failure;
      return RuntimeFailure(
        code: failure.code,
        semanticReason: failure.semanticReason,
        transportStatus: failure.transportStatus,
        origin: failure.origin,
        kind: failure.kind,
        nature: failure.nature,
        location: failure.location,
        context: failure.context,
        recovery: failure.recovery,
      );
    }
    if (error is TimeoutException) {
      return _localFailure(
        code: RuntimeFailureCodes.appTimeoutRequestTimeout,
        origin: RuntimeFailureOrigin.environment,
        kind: RuntimeFailureKind.timeout,
        nature: RuntimeFailureNature.transient,
        requestPath: requestPath,
        recovery: const RuntimeRecoveryDirective(
          action: 'retry',
          disruptionLevel: 'snackbar',
        ),
      );
    }
    if (error is CloudOperationCancelledException) {
      return _localFailure(
        code: RuntimeFailureCodes.appCancelledOperationCancelled,
        origin: RuntimeFailureOrigin.user,
        kind: RuntimeFailureKind.cancelled,
        nature: RuntimeFailureNature.permanent,
        requestPath: requestPath,
        recovery: const RuntimeRecoveryDirective(
          action: 'absorb',
          disruptionLevel: 'silent',
        ),
      );
    }
    if (error is http.ClientException) {
      return _localFailure(
        code: RuntimeFailureCodes.appNetworkOffline,
        origin: RuntimeFailureOrigin.environment,
        kind: RuntimeFailureKind.network,
        nature: RuntimeFailureNature.transient,
        requestPath: requestPath,
      );
    }
    if (error is ArgumentError || error is StateError) {
      return _localFailure(
        code: RuntimeFailureCodes.appContractInvalidResponse,
        origin: RuntimeFailureOrigin.developer,
        kind: RuntimeFailureKind.contract,
        nature: RuntimeFailureNature.bug,
        requestPath: requestPath,
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'errorType',
            value: error.runtimeType.toString(),
          ),
        ],
        recovery: const RuntimeRecoveryDirective(
          action: 'surface',
          disruptionLevel: 'inlineCard',
        ),
      );
    }
    if (error is FormatException) {
      return _localFailure(
        code: RuntimeFailureCodes.appContractInvalidJson,
        origin: RuntimeFailureOrigin.remoteDependency,
        kind: RuntimeFailureKind.parsing,
        nature: RuntimeFailureNature.bug,
        requestPath: requestPath,
        recovery: const RuntimeRecoveryDirective(
          action: 'surface',
          disruptionLevel: 'inlineCard',
        ),
      );
    }
    return _localFailure(
      code: RuntimeFailureCodes.appSystemUnknownError,
      kind: RuntimeFailureKind.internal,
      nature: RuntimeFailureNature.bug,
      requestPath: requestPath,
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(
          key: 'errorType',
          value: error.runtimeType.toString(),
        ),
      ],
    );
  }

  static RuntimeFailure runtimeFailureFromStatusCode(
    int statusCode, {
    String? body,
    String? requestPath,
  }) {
    final parsedResponse = _readRuntimeErrorResponse(
      body,
      transportStatus: statusCode,
    );
    if (parsedResponse != null) return parsedResponse.failure;
    final code = _readCode(body) ?? _codeFromStatus(statusCode);
    return RuntimeFailure(
      code: code,
      transportStatus: statusCode,
      origin: statusCode >= 500
          ? RuntimeFailureOrigin.remoteDependency
          : RuntimeFailureOrigin.user,
      kind: _kindFromStatus(statusCode),
      nature: _natureFromStatus(statusCode),
      location: const RuntimeFailureLocation(
        businessObject: 'cloud_request',
        functionModule: 'cloud_error_mapper',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'statusCode',
            value: statusCode.toString(),
          ),
          if (requestPath != null && requestPath.trim().isNotEmpty)
            RuntimeContextAttribute(key: 'requestPath', value: requestPath),
        ],
      ),
    );
  }

  /// Parse structured error code from the response body JSON {"code": "DOMAIN.KIND.reason"}.
  static String? _readCode(String? body) {
    if (body == null || body.isEmpty) return null;
    if (!body.contains('"code"')) return null;
    try {
      final map = jsonDecode(body);
      if (map is Map<String, dynamic>) {
        final code = map['code'];
        if (code is String && code.isNotEmpty) return code;
        // Nested under "error" field
        final err = map['error'];
        if (err is Map<String, dynamic>) {
          final c = err['code'];
          if (c is String && c.isNotEmpty) return c;
        }
      }
    } catch (_) {
      // If JSON decode fails, fall back to null rather than crashing.
    }
    return null;
  }

  static RuntimeErrorResponse? _readRuntimeErrorResponse(
    String? body, {
    int? transportStatus,
  }) {
    if (body == null || body.isEmpty || !body.contains('"code"')) return null;
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic> &&
          decoded['location'] is Map &&
          decoded['context'] is Map) {
        return RuntimeErrorResponse.fromJson(
          decoded,
          transportStatus: transportStatus,
        );
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  static String? parsedUserMessage(String? body) {
    final parsed = _readRuntimeErrorResponse(body);
    final userMessage = parsed?.userMessage.trim() ?? '';
    if (userMessage.isNotEmpty) {
      return userMessage;
    }
    if (body == null || body.isEmpty) {
      return null;
    }
    try {
      final decoded = jsonDecode(body);
      if (decoded is! Map<String, dynamic>) {
        return null;
      }
      final direct = _firstNonEmptyString(decoded, const <String>[
        'userMessage',
        'user_message',
        'message',
        'reasonMessage',
      ]);
      if (direct != null) {
        return direct;
      }
      final error = decoded['error'];
      if (error is Map<String, dynamic>) {
        return _firstNonEmptyString(error, const <String>[
          'userMessage',
          'user_message',
          'message',
          'reasonMessage',
        ]);
      }
    } catch (_) {
      return null;
    }
    return null;
  }
}

Duration? _parseRetryAfter(String? value) {
  final normalized = value?.trim() ?? '';
  final seconds = int.tryParse(normalized);
  if (seconds != null) {
    return seconds < 0 ? null : Duration(seconds: seconds);
  }
  final match = RegExp(
    r'^[A-Za-z]{3}, (\d{2}) ([A-Za-z]{3}) (\d{4}) '
    r'(\d{2}):(\d{2}):(\d{2}) GMT$',
  ).firstMatch(normalized);
  if (match == null) return null;
  const months = <String, int>{
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12,
  };
  final month = months[match.group(2)];
  if (month == null) return null;
  final retryAt = DateTime.utc(
    int.parse(match.group(3)!),
    month,
    int.parse(match.group(1)!),
    int.parse(match.group(4)!),
    int.parse(match.group(5)!),
    int.parse(match.group(6)!),
  );
  final delay = retryAt.difference(DateTime.now().toUtc());
  if (delay <= Duration.zero) return Duration.zero;
  return delay;
}

String? _firstNonEmptyString(Map<String, dynamic> map, List<String> keys) {
  for (final key in keys) {
    final value = map[key];
    if (value is String && value.trim().isNotEmpty) {
      return value.trim();
    }
  }
  return null;
}

RuntimeFailure _localFailure({
  required String code,
  RuntimeFailureOrigin origin = RuntimeFailureOrigin.localClient,
  required RuntimeFailureKind kind,
  required RuntimeFailureNature nature,
  String? requestPath,
  List<RuntimeContextAttribute> attributes = const <RuntimeContextAttribute>[],
  RuntimeRecoveryDirective recovery = const RuntimeRecoveryDirective.none(),
}) {
  return RuntimeFailure(
    code: code,
    origin: origin,
    kind: kind,
    nature: nature,
    location: const RuntimeFailureLocation(
      businessObject: 'app_runtime',
      functionModule: 'cloud_error_mapper',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        if (requestPath != null && requestPath.trim().isNotEmpty)
          RuntimeContextAttribute(key: 'requestPath', value: requestPath),
        ...attributes,
      ],
    ),
    recovery: recovery,
  );
}

CloudErrorType _cloudTypeFromFailure(RuntimeFailureBase failure) {
  return switch (failure.kind) {
    RuntimeFailureKind.timeout => CloudErrorType.timeout,
    RuntimeFailureKind.cancelled => CloudErrorType.cancelled,
    RuntimeFailureKind.network => CloudErrorType.network,
    RuntimeFailureKind.auth => CloudErrorType.unauthorized,
    RuntimeFailureKind.permission => CloudErrorType.forbidden,
    RuntimeFailureKind.notFound => CloudErrorType.notFound,
    RuntimeFailureKind.parsing ||
    RuntimeFailureKind.contract => CloudErrorType.invalidResponse,
    RuntimeFailureKind.unavailable => CloudErrorType.server,
    RuntimeFailureKind.rateLimited => CloudErrorType.rateLimited,
    _ => CloudErrorType.unknown,
  };
}

String _codeFromStatus(int statusCode) {
  if (statusCode == 401) return RuntimeFailureCodes.appUserUnauthorized;
  if (statusCode == 403) return RuntimeFailureCodes.appUserForbidden;
  if (statusCode == 404) return RuntimeFailureCodes.appUserNotFound;
  if (statusCode >= 500) return RuntimeFailureCodes.cloudSystemUnavailable;
  return RuntimeFailureCodes.cloudSystemUnknownError;
}

RuntimeFailureKind _kindFromStatus(int statusCode) {
  if (statusCode == 401) return RuntimeFailureKind.auth;
  if (statusCode == 403) return RuntimeFailureKind.permission;
  if (statusCode == 404) return RuntimeFailureKind.notFound;
  if (statusCode == 429) return RuntimeFailureKind.rateLimited;
  if (statusCode >= 500) return RuntimeFailureKind.unavailable;
  return RuntimeFailureKind.internal;
}

RuntimeFailureNature _natureFromStatus(int statusCode) {
  if (statusCode == 401 || statusCode == 403) {
    return RuntimeFailureNature.requiresUserAction;
  }
  if (statusCode == 429) return RuntimeFailureNature.transient;
  if (statusCode >= 500) return RuntimeFailureNature.transient;
  return RuntimeFailureNature.permanent;
}
