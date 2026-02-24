import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';

class CloudErrorMapper {
  const CloudErrorMapper._();

  static CloudException fromStatusCode(
    int statusCode, {
    String? body,
    String? requestPath,
  }) {
    final suffix = requestPath == null ? '' : ' ($requestPath)';
    if (statusCode == 401) {
      return CloudException(
        type: CloudErrorType.unauthorized,
        statusCode: statusCode,
        message: 'Unauthorized$suffix',
        code: _readCode(body),
      );
    }
    if (statusCode == 403) {
      return CloudException(
        type: CloudErrorType.forbidden,
        statusCode: statusCode,
        message: 'Forbidden$suffix',
        code: _readCode(body),
      );
    }
    if (statusCode == 404) {
      return CloudException(
        type: CloudErrorType.notFound,
        statusCode: statusCode,
        message: 'Not found$suffix',
        code: _readCode(body),
      );
    }
    if (statusCode >= 500) {
      return CloudException(
        type: CloudErrorType.server,
        statusCode: statusCode,
        message: 'Server error$suffix',
        code: _readCode(body),
      );
    }
    return CloudException(
      type: CloudErrorType.unknown,
      statusCode: statusCode,
      message: 'HTTP $statusCode$suffix',
      code: _readCode(body),
    );
  }

  // Keep decoder lightweight for P0; parse only if body is json-like text.
  static String? _readCode(String? body) {
    if (body == null || body.isEmpty) return null;
    final idx = body.indexOf('"code"');
    if (idx < 0) return null;
    return 'REMOTE_ERROR';
  }
}
