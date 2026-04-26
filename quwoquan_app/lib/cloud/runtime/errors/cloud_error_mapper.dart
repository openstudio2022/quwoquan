import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class CloudErrorMapper {
  const CloudErrorMapper._();

  static CloudException fromStatusCode(
    int statusCode, {
    String? body,
    String? requestPath,
  }) {
    final code = _readCode(body);
    final errorCode = _contentErrorCodeFromRuntimeCode(code);
    final runtimeFailure = runtimeFailureFromStatusCode(
      statusCode,
      body: body,
      requestPath: requestPath,
    );
    final suffix = requestPath == null ? '' : ' ($requestPath)';
    if (statusCode == 401) {
      return CloudException(
        type: CloudErrorType.unauthorized,
        statusCode: statusCode,
        message: 'Unauthorized$suffix',
        code: code,
        errorCode: errorCode,
        runtimeFailure: runtimeFailure,
      );
    }
    if (statusCode == 403) {
      return CloudException(
        type: CloudErrorType.forbidden,
        statusCode: statusCode,
        message: 'Forbidden$suffix',
        code: code,
        errorCode: errorCode,
        runtimeFailure: runtimeFailure,
      );
    }
    if (statusCode == 404) {
      return CloudException(
        type: CloudErrorType.notFound,
        statusCode: statusCode,
        message: 'Not found$suffix',
        code: code,
        errorCode: errorCode,
        runtimeFailure: runtimeFailure,
      );
    }
    if (statusCode >= 500) {
      return CloudException(
        type: CloudErrorType.server,
        statusCode: statusCode,
        message: 'Server error$suffix',
        code: code,
        errorCode: errorCode,
        runtimeFailure: runtimeFailure,
      );
    }
    return CloudException(
      type: CloudErrorType.unknown,
      statusCode: statusCode,
      message: 'HTTP $statusCode$suffix',
      code: code,
      errorCode: errorCode,
      runtimeFailure: runtimeFailure,
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
      code: 'APP.CONTRACT.invalid_response',
      origin: RuntimeFailureOrigin.localClient,
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
    );
  }

  static RuntimeFailure runtimeFailureFromException(
    Object error, {
    String? requestPath,
  }) {
    if (error is CloudException && error.runtimeFailure != null) {
      final failure = error.runtimeFailure!;
      if (failure is RuntimeFailure) return failure;
      return RuntimeFailure(
        code: failure.code,
        origin: failure.origin,
        kind: failure.kind,
        nature: failure.nature,
        location: failure.location,
        context: failure.context,
      );
    }
    if (error is TimeoutException) {
      return _localFailure(
        code: 'APP.TIMEOUT.request_timeout',
        kind: RuntimeFailureKind.timeout,
        nature: RuntimeFailureNature.transient,
        requestPath: requestPath,
      );
    }
    if (error is SocketException) {
      return _localFailure(
        code: 'APP.NETWORK.offline',
        kind: RuntimeFailureKind.network,
        nature: RuntimeFailureNature.transient,
        requestPath: requestPath,
      );
    }
    if (error is FormatException) {
      return _localFailure(
        code: 'APP.CONTRACT.invalid_json',
        kind: RuntimeFailureKind.parsing,
        nature: RuntimeFailureNature.bug,
        requestPath: requestPath,
      );
    }
    if (error is FileSystemException) {
      return _localFailure(
        code: 'APP.STORAGE.file_system_failure',
        kind: RuntimeFailureKind.storage,
        nature: RuntimeFailureNature.transient,
        requestPath: requestPath,
      );
    }
    if (error is PlatformException) {
      final permissionLike =
          error.code.toLowerCase().contains('permission') ||
          error.code.toLowerCase().contains('denied');
      return _localFailure(
        code: permissionLike
            ? 'APP.PERMISSION.platform_permission_denied'
            : 'APP.SYSTEM.platform_exception',
        kind: permissionLike
            ? RuntimeFailureKind.permission
            : RuntimeFailureKind.internal,
        nature: permissionLike
            ? RuntimeFailureNature.requiresPermission
            : RuntimeFailureNature.bug,
        requestPath: requestPath,
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'platformCode', value: error.code),
        ],
      );
    }
    return _localFailure(
      code: 'APP.SYSTEM.unknown_error',
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
    final parsedResponse = _readRuntimeErrorResponse(body);
    if (parsedResponse != null) return parsedResponse.failure;
    final code = _readCode(body) ?? _codeFromStatus(statusCode);
    return RuntimeFailure(
      code: code,
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

  static RuntimeErrorResponse? _readRuntimeErrorResponse(String? body) {
    if (body == null || body.isEmpty || !body.contains('"code"')) return null;
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic> &&
          decoded['location'] is Map &&
          decoded['context'] is Map) {
        return RuntimeErrorResponse.fromJson(decoded);
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  /// Map a structured error response body to a typed [ContentErrorCode].
  /// Returns [ContentErrorCode.unknown] when the code is absent or unrecognised.
  static ContentErrorCode fromErrorResponse(String? body) {
    final code = _readCode(body);
    if (code == null) return ContentErrorCode.unknown;
    return _contentErrorCodeFromRuntimeCode(code) ?? ContentErrorCode.unknown;
  }
}

RuntimeFailure _localFailure({
  required String code,
  required RuntimeFailureKind kind,
  required RuntimeFailureNature nature,
  String? requestPath,
  List<RuntimeContextAttribute> attributes = const <RuntimeContextAttribute>[],
}) {
  return RuntimeFailure(
    code: code,
    origin: RuntimeFailureOrigin.localClient,
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
  );
}

CloudErrorType _cloudTypeFromFailure(RuntimeFailureBase failure) {
  return switch (failure.kind) {
    RuntimeFailureKind.timeout => CloudErrorType.timeout,
    RuntimeFailureKind.network => CloudErrorType.network,
    RuntimeFailureKind.auth => CloudErrorType.unauthorized,
    RuntimeFailureKind.permission => CloudErrorType.forbidden,
    RuntimeFailureKind.notFound => CloudErrorType.notFound,
    RuntimeFailureKind.parsing ||
    RuntimeFailureKind.contract => CloudErrorType.invalidResponse,
    RuntimeFailureKind.unavailable => CloudErrorType.server,
    _ => CloudErrorType.unknown,
  };
}

ContentErrorCode? _contentErrorCodeFromRuntimeCode(String? code) {
  if (code == null || !code.startsWith('CONTENT.')) return null;
  return ContentErrorCode.fromCode(code);
}

String _codeFromStatus(int statusCode) {
  if (statusCode == 401) return 'APP.USER.unauthorized';
  if (statusCode == 403) return 'APP.USER.forbidden';
  if (statusCode == 404) return 'APP.USER.not_found';
  if (statusCode >= 500) return 'CLOUD.SYSTEM.unavailable';
  return 'CLOUD.SYSTEM.unknown_error';
}

RuntimeFailureKind _kindFromStatus(int statusCode) {
  if (statusCode == 401) return RuntimeFailureKind.auth;
  if (statusCode == 403) return RuntimeFailureKind.permission;
  if (statusCode == 404) return RuntimeFailureKind.notFound;
  if (statusCode >= 500) return RuntimeFailureKind.unavailable;
  return RuntimeFailureKind.internal;
}

RuntimeFailureNature _natureFromStatus(int statusCode) {
  if (statusCode == 401 || statusCode == 403) {
    return RuntimeFailureNature.requiresUserAction;
  }
  if (statusCode >= 500) return RuntimeFailureNature.transient;
  return RuntimeFailureNature.permanent;
}
