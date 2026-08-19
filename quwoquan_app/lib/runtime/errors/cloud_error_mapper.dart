import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_app/runtime/errors/cloud_transport_failure.dart';
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
    return fromDecodedStatusCode(
      statusCode,
      body: _tryDecodeJsonBody(body),
      requestPath: requestPath,
      retryAfter: retryAfter,
    );
  }

  /// Maps an HTTP failure whose JSON body has already been decoded by the
  /// shared, cancellable Cloud decoder.
  ///
  /// Generated operations use this entrypoint so a large error response does
  /// not synchronously decode the same body several times on the UI isolate.
  static CloudException fromDecodedStatusCode(
    int statusCode, {
    Object? body,
    String? requestPath,
    String? retryAfter,
  }) {
    final code = _readCodeFromDecoded(body);
    final domainErrorCode = DomainErrorCodeRegistry.fromCode(code);
    final runtimeResponse = _tryReadRuntimeErrorResponseFromDecoded(
      body,
      transportStatus: statusCode,
    );
    final runtimeFailure = _runtimeFailureFromDecodedStatusCode(
      statusCode,
      body: body,
      requestPath: requestPath,
      parsedResponse: runtimeResponse,
    );
    final userMessage = _parsedUserMessageFromDecodedBody(
      body,
      runtimeResponse,
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
        userMessage: userMessage,
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
        userMessage: userMessage,
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
        userMessage: userMessage,
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
        userMessage: userMessage,
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
      userMessage: userMessage,
      requestId: runtimeResponse?.requestId,
      traceId: runtimeResponse?.traceId,
      retryAfter: retryDelay,
    );
  }

  static CloudException fromException(
    Object error, {
    String? requestPath,
    CloudTransportFailure? transportFailure,
  }) {
    final runtimeFailure = runtimeFailureFromException(
      error,
      requestPath: requestPath,
      transportFailure: transportFailure,
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
    CloudTransportFailure? transportFailure,
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
    if (transportFailure != null) {
      return _transportFailure(transportFailure, requestPath: requestPath);
    }
    if (error is http.ClientException) {
      return _localFailure(
        code: RuntimeFailureCodes.appNetworkConnectionFailed,
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

  static RuntimeFailure _transportFailure(
    CloudTransportFailure failure, {
    String? requestPath,
  }) {
    final code = switch (failure.reason) {
      CloudTransportFailureReason.secureConnection =>
        RuntimeFailureCodes.appNetworkSecureConnectionFailed,
      CloudTransportFailureReason.connectionRefused =>
        RuntimeFailureCodes.appNetworkConnectionRefused,
      CloudTransportFailureReason.nameResolution =>
        RuntimeFailureCodes.appNetworkNameResolutionFailed,
      CloudTransportFailureReason.offline =>
        RuntimeFailureCodes.appNetworkOffline,
      CloudTransportFailureReason.connectionFailed =>
        RuntimeFailureCodes.appNetworkConnectionFailed,
    };
    return _localFailure(
      code: code,
      origin: code == RuntimeFailureCodes.appNetworkConnectionRefused
          ? RuntimeFailureOrigin.remoteDependency
          : RuntimeFailureOrigin.environment,
      kind: RuntimeFailureKind.network,
      nature: failure.reason == CloudTransportFailureReason.secureConnection
          ? RuntimeFailureNature.permanent
          : RuntimeFailureNature.transient,
      requestPath: requestPath,
      attributes: <RuntimeContextAttribute>[
        if (failure.platformErrorCode != null)
          RuntimeContextAttribute(
            key: 'platformErrorCode',
            value: '${failure.platformErrorCode}',
          ),
      ],
    );
  }

  static RuntimeFailure runtimeFailureFromStatusCode(
    int statusCode, {
    String? body,
    String? requestPath,
  }) {
    return runtimeFailureFromDecodedStatusCode(
      statusCode,
      body: _tryDecodeJsonBody(body),
      requestPath: requestPath,
    );
  }

  static RuntimeFailure runtimeFailureFromDecodedStatusCode(
    int statusCode, {
    Object? body,
    String? requestPath,
  }) {
    final parsedResponse = _tryReadRuntimeErrorResponseFromDecoded(
      body,
      transportStatus: statusCode,
    );
    return _runtimeFailureFromDecodedStatusCode(
      statusCode,
      body: body,
      requestPath: requestPath,
      parsedResponse: parsedResponse,
    );
  }

  static RuntimeFailure _runtimeFailureFromDecodedStatusCode(
    int statusCode, {
    required Object? body,
    required String? requestPath,
    required RuntimeErrorResponse? parsedResponse,
  }) {
    if (parsedResponse != null) return parsedResponse.failure;
    final code = _readCodeFromDecoded(body) ?? _codeFromStatus(statusCode);
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

  static String? _readCodeFromDecoded(Object? body) {
    if (body is Map<String, dynamic>) {
      final code = body['code'];
      if (code is String && code.isNotEmpty) return code;
      // Nested under "error" field.
      final error = body['error'];
      if (error is Map<String, dynamic>) {
        final nestedCode = error['code'];
        if (nestedCode is String && nestedCode.isNotEmpty) {
          return nestedCode;
        }
      }
    }
    return null;
  }

  static RuntimeErrorResponse? _tryReadRuntimeErrorResponseFromDecoded(
    Object? body, {
    int? transportStatus,
  }) {
    try {
      if (body is Map<String, dynamic> &&
          body['location'] is Map &&
          body['context'] is Map) {
        return RuntimeErrorResponse.fromJson(
          body,
          transportStatus: transportStatus,
        );
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  static String? parsedUserMessage(String? body) {
    return _parsedUserMessageFromDecoded(_tryDecodeJsonBody(body));
  }

  static String? _parsedUserMessageFromDecoded(Object? body) {
    return _parsedUserMessageFromDecodedBody(
      body,
      _tryReadRuntimeErrorResponseFromDecoded(body),
    );
  }

  static String? _parsedUserMessageFromDecodedBody(
    Object? body,
    RuntimeErrorResponse? parsedResponse,
  ) {
    final userMessage = parsedResponse?.userMessage.trim() ?? '';
    if (userMessage.isNotEmpty) {
      return userMessage;
    }
    if (body is! Map<String, dynamic>) {
      return null;
    }
    final canonical = body['userMessage'];
    if (canonical is String && canonical.trim().isNotEmpty) {
      return canonical.trim();
    }
    return null;
  }
}

Object? _tryDecodeJsonBody(String? body) {
  if (body == null || body.isEmpty) return null;
  try {
    return jsonDecode(body);
  } catch (_) {
    // Malformed error bodies retain the historical status-code fallback.
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
  if (statusCode == 400 || statusCode == 409 || statusCode == 422) {
    return RuntimeFailureKind.validation;
  }
  if (statusCode == 429) return RuntimeFailureKind.rateLimited;
  if (statusCode == 504) return RuntimeFailureKind.timeout;
  if (statusCode == 500) return RuntimeFailureKind.internal;
  if (statusCode >= 500) return RuntimeFailureKind.unavailable;
  return RuntimeFailureKind.internal;
}

RuntimeFailureNature _natureFromStatus(int statusCode) {
  if (statusCode == 401 || statusCode == 403) {
    return RuntimeFailureNature.requiresUserAction;
  }
  if (statusCode == 429) return RuntimeFailureNature.transient;
  if (statusCode == 409) return RuntimeFailureNature.transient;
  if (statusCode >= 500) return RuntimeFailureNature.transient;
  return RuntimeFailureNature.permanent;
}
