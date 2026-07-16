import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';

class CloudResponseDecoder {
  const CloudResponseDecoder._();

  static CloudJsonMap asObject(Object? decoded, {String? context}) {
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) {
      return Map<String, dynamic>.from(decoded);
    }
    throw CloudErrorMapper.invalidResponse(
      message: 'Invalid object response${context == null ? '' : ': $context'}',
      requestPath: context,
    );
  }

  static CursorPage<CloudJsonMap> asCursorPage(
    Object? decoded, {
    String? context,
  }) {
    final obj = asObject(decoded, context: context);
    final rawItems = obj['items'];
    if (rawItems is! List) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Missing items${context == null ? '' : ': $context'}',
        requestPath: context,
      );
    }
    final items = <CloudJsonMap>[];
    for (var index = 0; index < rawItems.length; index++) {
      final raw = rawItems[index];
      if (raw is! Map) {
        throw _invalidListElement(key: 'items', index: index, context: context);
      }
      items.add(Map<String, dynamic>.from(raw));
    }
    final nextCursor = obj['nextCursor']?.toString();
    final rawTotalCount = obj['totalCount'] ?? obj['total'];
    final totalCount = rawTotalCount is num
        ? rawTotalCount.toInt()
        : int.tryParse(rawTotalCount?.toString() ?? '');
    return CursorPage<CloudJsonMap>(
      items: items,
      nextCursor: nextCursor,
      totalCount: totalCount,
    );
  }

  /// 从已解码对象中读取 `key` 对应的 `List<Map>`。
  ///
  /// 缺省字段可表达可选空列表；一旦字段存在，值和每个元素必须严格符合
  /// wire contract，禁止把坏响应静默裁剪为部分成功。
  static List<CloudJsonMap> mapList(
    CloudJsonMap obj,
    String key, {
    String? context,
  }) {
    final raw = obj[key];
    if (raw == null && !obj.containsKey(key)) {
      return const <Map<String, dynamic>>[];
    }
    if (raw is! List) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Invalid $key list${context == null ? '' : ': $context'}',
        requestPath: context,
      );
    }
    final out = <Map<String, dynamic>>[];
    for (var index = 0; index < raw.length; index++) {
      final element = raw[index];
      if (element is! Map) {
        throw _invalidListElement(key: key, index: index, context: context);
      }
      final e = element;
      if (e is Map<String, dynamic>) {
        out.add(e);
      } else {
        out.add(Map<String, dynamic>.from(e));
      }
    }
    return out;
  }

  /// 按顺序查找 `keys` 中第一个存在于 `obj` 的键，解析为 [List<Map<String, dynamic>>]。
  /// 若均不存在则返回空列表；存在但不是 List 时视为 wire contract 违例。
  static List<CloudJsonMap> mapListFirstPresent(
    CloudJsonMap obj,
    List<String> keys, {
    String? context,
  }) {
    for (final key in keys) {
      if (obj.containsKey(key)) {
        return mapList(obj, key, context: context);
      }
    }
    return const <Map<String, dynamic>>[];
  }

  /// 按顺序尝试 `keys`，返回首个 **非空** 的 `List<Map>`（与 persona summary 等多键列表别名一致）。
  static List<CloudJsonMap> mapListFirstNonEmpty(
    CloudJsonMap obj,
    List<String> keys, {
    String? context,
  }) {
    for (final key in keys) {
      final list = mapList(obj, key, context: context);
      if (list.isNotEmpty) {
        return list;
      }
    }
    return const <Map<String, dynamic>>[];
  }

  static CloudException _invalidListElement({
    required String key,
    required int index,
    required String? context,
  }) {
    return CloudErrorMapper.invalidResponse(
      message:
          'Invalid $key list element at index $index'
          '${context == null ? '' : ': $context'}',
      requestPath: context,
    );
  }
}
