import 'dart:convert';

import 'package:quwoquan_app/runtime/observability/generated/runtime_log_catalog.g.dart';

final class RuntimeLogRedactor {
  const RuntimeLogRedactor();

  static const String masked = '***';
  static const int maxAttributeCount = RuntimeLogCatalog.maxAttributes;
  static const int maxKeyLength = RuntimeLogCatalog.maxAttributeKeyLength;
  static const int maxValueLength = RuntimeLogCatalog.maxAttributeValueLength;

  Map<String, String> redactAttributes(Map<String, String> input) {
    final output = <String, String>{};
    for (final entry in input.entries.take(maxAttributeCount)) {
      final key = _bounded(entry.key.trim(), maxKeyLength);
      if (key.isEmpty) continue;
      final normalizedKey = key.toLowerCase().replaceAll(
        RegExp(r'[^a-z0-9]'),
        '',
      );
      if (_mustDropKey(normalizedKey)) continue;
      final value = _bounded(redactText(entry.value), maxValueLength);
      final candidate = <String, String>{...output, key: value};
      if (utf8.encode(jsonEncode(candidate)).length >
          RuntimeLogCatalog.maxAttributesBytes) {
        break;
      }
      output[key] = value;
    }
    return Map<String, String>.unmodifiable(output);
  }

  bool _mustDropKey(String normalizedKey) =>
      RuntimeLogCatalog.forbiddenAttributeKeys.any(
        (key) => _matchesForbiddenKey(normalizedKey, key),
      ) ||
      RuntimeLogCatalog.highCardinalityMetricKeys.any(
        (key) => _matchesForbiddenKey(normalizedKey, key),
      ) ||
      RuntimeLogCatalog.forbiddenFields.any(
        (field) => _matchesForbiddenKey(normalizedKey, field),
      );

  bool _matchesForbiddenKey(String normalizedKey, String forbiddenKey) {
    final normalizedForbidden = forbiddenKey.toLowerCase().replaceAll(
      RegExp(r'[^a-z0-9]'),
      '',
    );
    return normalizedKey == normalizedForbidden ||
        (normalizedForbidden != 'ip' &&
            normalizedKey.contains(normalizedForbidden));
  }

  String redactText(String input) {
    var value = input;
    value = value.replaceAll(
      RegExp(r'\bBearer\s+[A-Za-z0-9._~+/=-]+', caseSensitive: false),
      'Bearer $masked',
    );
    value = value.replaceAllMapped(
      RegExp(
        r'([?&](?:access_token|token|authcode|authorization|signature|'
        r'x-amz-signature|x-amz-credential|secret)=)[^&#\s]+',
        caseSensitive: false,
      ),
      (match) => '${match.group(1)}$masked',
    );
    value = value.replaceAll(
      RegExp(
        r'\b(?:\d{3}[- ]?\d{4}[- ]?\d{4}|'
        r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b',
      ),
      masked,
    );
    return _bounded(value, maxValueLength);
  }

  String _bounded(String value, int limit) {
    if (value.length <= limit) return value;
    return '${value.substring(0, limit)}…';
  }
}
