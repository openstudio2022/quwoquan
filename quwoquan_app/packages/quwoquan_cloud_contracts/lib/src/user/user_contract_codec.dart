/// User 领域 pure contract 的 JSON 边界解码器。
///
/// 仅供 `src/user/**_contracts.dart` 内部使用；业务调用方只接触强类型 query、
/// projection 与 slice，不接触动态 wire。
final class UserContractCodec {
  const UserContractCodec._();

  static Map<Object?, Object?> object(Object? value, String label) {
    if (value is! Map<Object?, Object?>) {
      throw FormatException('$label must be a JSON object');
    }
    return value;
  }

  static List<Map<Object?, Object?>> objectList(Object? value, String label) {
    if (value == null) return const <Map<Object?, Object?>>[];
    if (value is! List<Object?>) {
      throw FormatException('$label must be a JSON array');
    }
    return List<Map<Object?, Object?>>.unmodifiable(
      value.map((item) => object(item, '$label item')),
    );
  }

  static String requiredText(
    Map<Object?, Object?> source,
    String key, {
    String? label,
  }) {
    final value = optionalText(source[key]);
    if (value == null) {
      throw FormatException('${label ?? key} must be a non-empty string');
    }
    return value;
  }

  static String textOr(
    Map<Object?, Object?> source,
    String key,
    String fallback,
  ) {
    return optionalText(source[key]) ?? fallback;
  }

  static String? optionalText(Object? value) {
    if (value == null) return null;
    if (value is! String) {
      throw const FormatException('expected a string');
    }
    final normalized = value.trim();
    return normalized.isEmpty ? null : normalized;
  }

  static bool booleanOr(
    Map<Object?, Object?> source,
    String key,
    bool fallback,
  ) {
    final value = source[key];
    if (value == null) return fallback;
    if (value is! bool) {
      throw FormatException('$key must be a bool');
    }
    return value;
  }

  static bool? optionalBoolean(
    Map<Object?, Object?> source,
    String key,
  ) {
    final value = source[key];
    if (value == null) return null;
    if (value is! bool) {
      throw FormatException('$key must be a bool');
    }
    return value;
  }

  static int integerOr(
    Map<Object?, Object?> source,
    String key,
    int fallback,
  ) {
    final value = source[key];
    if (value == null) return fallback;
    if (value is num) return value.toInt();
    throw FormatException('$key must be a number');
  }

  static DateTime? optionalTimestamp(
    Map<Object?, Object?> source,
    String key,
  ) {
    final value = source[key];
    if (value == null) return null;
    if (value is DateTime) return value.toUtc();
    if (value is String) {
      final parsed = DateTime.tryParse(value);
      if (parsed != null) return parsed.toUtc();
    }
    throw FormatException('$key must be an RFC3339 timestamp');
  }

  static List<String> stringList(Object? value, String label) {
    if (value == null) return const <String>[];
    if (value is! List<Object?>) {
      throw FormatException('$label must be a JSON array');
    }
    return List<String>.unmodifiable(
      value.map((item) {
        if (item is! String) {
          throw FormatException('$label items must be strings');
        }
        return item.trim();
      }).where((item) => item.isNotEmpty),
    );
  }
}
