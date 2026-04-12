import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';

class CloudResponseDecoder {
  const CloudResponseDecoder._();

  static CloudJsonMap asObject(Object? decoded, {String? context}) {
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) {
      return Map<String, dynamic>.from(decoded);
    }
    throw CloudException(
      type: CloudErrorType.invalidResponse,
      message: 'Invalid object response${context == null ? '' : ': $context'}',
    );
  }

  static CursorPage<CloudJsonMap> asCursorPage(
    Object? decoded, {
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
    final items = <CloudJsonMap>[];
    for (final raw in rawItems) {
      if (raw is! Map) {
        continue;
      }
      items.add(Map<String, dynamic>.from(raw));
    }
    final nextCursor = obj['nextCursor']?.toString();
    return CursorPage<CloudJsonMap>(items: items, nextCursor: nextCursor);
  }

  /// 从已解码对象中读取 `key` 对应的 `List<Map>`（忽略非 Map 元素），避免 `List<dynamic>.cast` 主路径。
  static List<CloudJsonMap> mapList(
    CloudJsonMap obj,
    String key,
  ) {
    final raw = obj[key];
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    final out = <Map<String, dynamic>>[];
    for (final e in raw) {
      if (e is Map<String, dynamic>) {
        out.add(e);
      } else if (e is Map) {
        out.add(Map<String, dynamic>.from(e));
      }
    }
    return out;
  }

  /// 按顺序查找 `keys` 中第一个存在于 `obj` 且值为 [List] 的键，解析为 [List<Map<String, dynamic>>]（忽略非 Map 元素）。
  /// 若均不存在或非 List，返回空列表。
  static List<CloudJsonMap> mapListFirstPresent(
    CloudJsonMap obj,
    List<String> keys,
  ) {
    for (final key in keys) {
      final raw = obj[key];
      if (raw is List) {
        return mapList(obj, key);
      }
    }
    return const <Map<String, dynamic>>[];
  }

  /// 按顺序尝试 `keys`，返回首个 **非空** 的 `List<Map>`（与 persona summary 等多键列表别名一致）。
  static List<CloudJsonMap> mapListFirstNonEmpty(
    CloudJsonMap obj,
    List<String> keys,
  ) {
    for (final key in keys) {
      final list = mapList(obj, key);
      if (list.isNotEmpty) {
        return list;
      }
    }
    return const <Map<String, dynamic>>[];
  }
}
