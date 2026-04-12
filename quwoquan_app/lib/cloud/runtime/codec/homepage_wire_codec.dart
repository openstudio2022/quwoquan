import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

/// 主页 Entity JSON 子树收窄（手写 [HomepageDetail] 等与 wire 边界共用）。
abstract final class HomepageWireCodec {
  HomepageWireCodec._();

  /// 非 Map 或 null 时返回空 Map（与历史 `_homepageWireMap` 一致）。
  static CloudJsonMap stringKeyMapOrEmpty(Object? value) {
    if (value is! Map) {
      return const <String, dynamic>{};
    }
    return Map<String, dynamic>.from(value);
  }

  /// 非 List 或 null 时返回不可变空列表；元素非 Map 则跳过。
  static List<T> mapList<T>(
    Object? raw,
    T Function(CloudJsonMap m) build,
  ) {
    if (raw is! List) {
      return List<T>.empty(growable: false);
    }
    final out = <T>[];
    for (final item in raw) {
      if (item is! Map) {
        continue;
      }
      out.add(build(Map<String, dynamic>.from(item)));
    }
    return out;
  }

  /// 空串与仅空白视为 null。
  static String? optionalTrimmedString(Object? value) {
    final raw = (value ?? '').toString().trim();
    return raw.isEmpty ? null : raw;
  }

  static double? optionalDouble(Object? value) {
    return (value as num?)?.toDouble();
  }

  static DateTime? optionalDateTime(Object? value) {
    final raw = (value ?? '').toString().trim();
    if (raw.isEmpty) {
      return null;
    }
    return DateTime.tryParse(raw);
  }
}
