import 'dart:convert';

import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';

class CloudErrorMapper {
  const CloudErrorMapper._();

  static CloudException fromStatusCode(
    int statusCode, {
    String? body,
    String? requestPath,
  }) {
    final code = _readCode(body);
    final errorCode = code != null ? ContentErrorCode.fromCode(code) : null;
    final suffix = requestPath == null ? '' : ' ($requestPath)';
    if (statusCode == 401) {
      return CloudException(
        type: CloudErrorType.unauthorized,
        statusCode: statusCode,
        message: 'Unauthorized$suffix',
        code: code,
        errorCode: errorCode,
      );
    }
    if (statusCode == 403) {
      return CloudException(
        type: CloudErrorType.forbidden,
        statusCode: statusCode,
        message: 'Forbidden$suffix',
        code: code,
        errorCode: errorCode,
      );
    }
    if (statusCode == 404) {
      return CloudException(
        type: CloudErrorType.notFound,
        statusCode: statusCode,
        message: 'Not found$suffix',
        code: code,
        errorCode: errorCode,
      );
    }
    if (statusCode >= 500) {
      return CloudException(
        type: CloudErrorType.server,
        statusCode: statusCode,
        message: 'Server error$suffix',
        code: code,
        errorCode: errorCode,
      );
    }
    return CloudException(
      type: CloudErrorType.unknown,
      statusCode: statusCode,
      message: 'HTTP $statusCode$suffix',
      code: code,
      errorCode: errorCode,
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

  /// Map a structured error response body to a typed [ContentErrorCode].
  /// Returns [ContentErrorCode.unknown] when the code is absent or unrecognised.
  static ContentErrorCode fromErrorResponse(String? body) {
    final code = _readCode(body);
    if (code == null) return ContentErrorCode.unknown;
    return ContentErrorCode.fromCode(code);
  }
}
