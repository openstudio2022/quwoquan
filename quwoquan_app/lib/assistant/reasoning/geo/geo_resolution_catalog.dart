import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

class GeoResolutionCatalog {
  const GeoResolutionCatalog({
    this.timezoneCountryCodes = const <String, String>{},
    this.countryLabels = const <String, String>{},
  });

  static const String assetPath =
      'assets/assistant/config/geo_resolution_config.json';

  static GeoResolutionCatalog _cached = const GeoResolutionCatalog();
  static bool _loaded = false;

  final Map<String, String> timezoneCountryCodes;
  final Map<String, String> countryLabels;

  static Future<GeoResolutionCatalog> load({bool forceRefresh = false}) async {
    if (_loaded && !forceRefresh) {
      return _cached;
    }
    try {
      final raw = await rootBundle
          .loadString(assetPath)
          .timeout(const Duration(seconds: 3));
      final decoded = jsonDecode(raw);
      if (decoded is Map) {
        _cached = GeoResolutionCatalog.fromJson(
          decoded.cast<String, dynamic>(),
        );
        _loaded = true;
        return _cached;
      }
    } catch (_) {
      // Fall back to empty catalog to avoid blocking the assistant.
    }
    _cached = const GeoResolutionCatalog();
    _loaded = true;
    return _cached;
  }

  factory GeoResolutionCatalog.fromJson(Map<String, dynamic> json) {
    return GeoResolutionCatalog(
      timezoneCountryCodes: _normalizedStringMap(json['timezoneCountryCodes']),
      countryLabels: _normalizedStringMap(
        json['countryLabels'],
        normalizeKey: (value) => value.toUpperCase(),
      ),
    );
  }

  String resolveCountryCode({
    String locale = '',
    String timezone = '',
  }) {
    final localeMatch =
        RegExp(r'[_-]([A-Za-z]{2})$').firstMatch(locale.trim());
    if (localeMatch != null) {
      final code = (localeMatch.group(1) ?? '').trim().toUpperCase();
      if (code.isNotEmpty) {
        return code;
      }
    }
    return timezoneCountryCodes[timezone.trim()] ?? '';
  }

  String countryLabelFor(String countryCode) {
    return countryLabels[countryCode.trim().toUpperCase()] ?? '';
  }

  static Map<String, String> _normalizedStringMap(
    Object? raw, {
    String Function(String value)? normalizeKey,
  }) {
    if (raw is! Map) {
      return const <String, String>{};
    }
    final out = <String, String>{};
    for (final entry in raw.entries) {
      final key = (normalizeKey == null
              ? entry.key.toString().trim()
              : normalizeKey(entry.key.toString().trim()))
          .trim();
      final value = entry.value.toString().trim();
      if (key.isEmpty || value.isEmpty) {
        continue;
      }
      out[key] = value;
    }
    return out;
  }
}
