// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — `SlotValueSnapshot.value` 在 metadata 为 `type: any`，
// 业务侧应通过本类读取，避免把 `dynamic` 直接传入深层逻辑。

/// 槽位 `value` 字段的显式解码（不改动 wire 形状）。
class SlotValueCodec {
  SlotValueCodec._();

  /// 规范化字符串；`null` 与非 String 返回 `null`。
  static String? asTrimmedString(Object? value) {
    if (value is String) {
      final t = value.trim();
      return t.isEmpty ? null : t;
    }
    if (value != null) {
      final t = value.toString().trim();
      return t.isEmpty ? null : t;
    }
    return null;
  }

  static bool? asBool(Object? value) {
    if (value is bool) return value;
    if (value is String) {
      final s = value.trim().toLowerCase();
      if (s == 'true') return true;
      if (s == 'false') return false;
    }
    return null;
  }

  static int? asInt(Object? value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value.trim());
    return null;
  }

  static double? asDouble(Object? value) {
    if (value is double) return value;
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value.trim());
    return null;
  }

  /// Map 或 JSON 对象；否则 `null`。
  static Map<String, dynamic>? asStringKeyedMap(Object? value) {
    if (value is Map) {
      return value.map(
        (k, v) => MapEntry(k.toString(), v),
      );
    }
    return null;
  }

  /// 槽位合并/可用性判断用的单一字符串视图（与 [ConversationStateKernel] 历史行为一致）。
  static String displayForSlotMerge(Object? value) =>
      asTrimmedString(value) ?? (value?.toString().trim() ?? '');
}
