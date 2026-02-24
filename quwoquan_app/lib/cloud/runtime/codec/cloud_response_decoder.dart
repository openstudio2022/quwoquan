import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';

class CloudResponseDecoder {
  const CloudResponseDecoder._();

  static Map<String, dynamic> asObject(dynamic decoded, {String? context}) {
    if (decoded is Map<String, dynamic>) return decoded;
    throw CloudException(
      type: CloudErrorType.invalidResponse,
      message: 'Invalid object response${context == null ? '' : ': $context'}',
    );
  }

  static CursorPage<Map<String, dynamic>> asCursorPage(
    dynamic decoded, {
    String? context,
  }) {
    final obj = asObject(decoded, context: context);
    final rawItems = obj['items'];
    if (rawItems is! List) {
      throw CloudException(
        type: CloudErrorType.invalidResponse,
        message: 'Missing items${context == null ? '' : ': $context'}',
      );
    }
    final items = rawItems
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
    final nextCursor = obj['nextCursor']?.toString();
    return CursorPage<Map<String, dynamic>>(items: items, nextCursor: nextCursor);
  }
}
