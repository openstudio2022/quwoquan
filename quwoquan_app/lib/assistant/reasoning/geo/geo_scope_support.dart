import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';

class ResolvedGeoScope {
  const ResolvedGeoScope({
    this.geoKind = 'none',
    this.countryCode = '',
    this.countryLabel = '',
    this.regionLabel = '',
    this.cityLabel = '',
    this.marketCode = '',
    this.marketLabel = '',
    this.resolvedText = '',
    this.source = '',
    this.defaultApplied = false,
    this.reason = '',
  });

  final String geoKind;
  final String countryCode;
  final String countryLabel;
  final String regionLabel;
  final String cityLabel;
  final String marketCode;
  final String marketLabel;
  final String resolvedText;
  final String source;
  final bool defaultApplied;
  final String reason;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'geoKind': geoKind,
    'countryCode': countryCode,
    'countryLabel': countryLabel,
    'regionLabel': regionLabel,
    'cityLabel': cityLabel,
    'marketCode': marketCode,
    'marketLabel': marketLabel,
    'resolvedText': resolvedText,
    'source': source,
    'defaultApplied': defaultApplied,
    'reason': reason,
  };

  factory ResolvedGeoScope.fromJson(Map<String, dynamic> json) {
    return ResolvedGeoScope(
      geoKind: (json['geoKind'] as String?)?.trim() ?? 'none',
      countryCode: (json['countryCode'] as String?)?.trim() ?? '',
      countryLabel: (json['countryLabel'] as String?)?.trim() ?? '',
      regionLabel: (json['regionLabel'] as String?)?.trim() ?? '',
      cityLabel: (json['cityLabel'] as String?)?.trim() ?? '',
      marketCode: (json['marketCode'] as String?)?.trim() ?? '',
      marketLabel: (json['marketLabel'] as String?)?.trim() ?? '',
      resolvedText: (json['resolvedText'] as String?)?.trim() ?? '',
      source: (json['source'] as String?)?.trim() ?? '',
      defaultApplied: json['defaultApplied'] == true,
      reason: (json['reason'] as String?)?.trim() ?? '',
    );
  }
}

class DefaultGeoPolicy {
  const DefaultGeoPolicy({
    this.defaultGeoScope = 'none',
    this.fallbackAllowed = false,
    this.fallbackSources = const <String>[],
    this.marketTemplate = '',
    this.marketOverrides = const <String, String>{},
  });

  final String defaultGeoScope;
  final bool fallbackAllowed;
  final List<String> fallbackSources;
  final String marketTemplate;
  final Map<String, String> marketOverrides;
}

DefaultGeoPolicy parseDefaultGeoPolicy(Map<String, dynamic> retrievalPolicy) {
  final raw =
      (retrievalPolicy['defaultGeoPolicy'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final overrides = <String, String>{};
  final rawOverrides =
      (raw['marketOverrides'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  for (final entry in rawOverrides.entries) {
    final key = entry.key.trim().toUpperCase();
    final value = entry.value.toString().trim();
    if (key.isEmpty || value.isEmpty) {
      continue;
    }
    overrides[key] = value;
  }
  return DefaultGeoPolicy(
    defaultGeoScope: _stringValue(raw['defaultGeoScope']).toLowerCase(),
    fallbackAllowed: raw['fallbackAllowed'] == true,
    fallbackSources: _stringList(raw['fallbackSources']),
    marketTemplate: _stringValue(raw['marketTemplate']),
    marketOverrides: overrides,
  );
}

bool hasAvailableGeoContext(AvailableGeoContext context) {
  return context.countryCode.trim().isNotEmpty ||
      context.countryLabel.trim().isNotEmpty ||
      context.regionLabel.trim().isNotEmpty ||
      context.cityLabel.trim().isNotEmpty ||
      context.districtLabel.trim().isNotEmpty ||
      context.timezone.trim().isNotEmpty;
}

bool hasResolvedGeoScope(ResolvedGeoScope scope) {
  return scope.resolvedText.trim().isNotEmpty ||
      scope.cityLabel.trim().isNotEmpty ||
      scope.marketLabel.trim().isNotEmpty ||
      scope.countryLabel.trim().isNotEmpty ||
      scope.countryCode.trim().isNotEmpty;
}

AvailableGeoContext buildAvailableGeoContext({
  Map<String, dynamic> gpsLocation = const <String, dynamic>{},
  Map<String, dynamic> scopeHint = const <String, dynamic>{},
  AvailableGeoContext seed = const AvailableGeoContext(),
}) {
  final explicit = scopeHint['availableGeoContext'] is Map
      ? AvailableGeoContext.fromJson(
          (scopeHint['availableGeoContext'] as Map).cast<String, dynamic>(),
        )
      : seed;
  final gpsNested =
      (gpsLocation['location'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final scopeDevice =
      (scopeHint['device'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final locale = _firstNonEmpty(<String>[
    explicit.source == 'device_locale' ? explicit.countryCode : '',
    _stringValue(scopeHint['locale']),
    _stringValue(scopeHint['deviceLocale']),
    _stringValue(scopeDevice['locale']),
    _stringValue(gpsLocation['locale']),
  ]);
  final timezone = _firstNonEmpty(<String>[
    explicit.timezone,
    _stringValue(scopeHint['timezone']),
    _stringValue(scopeHint['deviceTimezone']),
    _stringValue(scopeDevice['timezone']),
    _stringValue(gpsLocation['timezone']),
  ]);
  final countryCode = _firstNonEmpty(<String>[
    explicit.countryCode,
    _stringValue(scopeHint['countryCode']).toUpperCase(),
    _stringValue(gpsLocation['countryCode']).toUpperCase(),
    _countryCodeFromLocale(locale),
  ]);
  final regionCode = _firstNonEmpty(<String>[
    explicit.regionCode,
    _stringValue(scopeHint['regionCode']),
    _stringValue(gpsLocation['regionCode']),
  ]);
  final regionLabel = _firstNonEmpty(<String>[
    explicit.regionLabel,
    _stringValue(scopeHint['regionLabel']),
    _stringValue(scopeHint['province']),
    _stringValue(scopeHint['region']),
    _stringValue(gpsLocation['regionLabel']),
    _stringValue(gpsLocation['province']),
  ]);
  final cityLabel = _firstNonEmpty(<String>[
    explicit.cityLabel,
    _stringValue(scopeHint['cityLabel']),
    _stringValue(scopeHint['city']),
    _stringValue(gpsLocation['cityLabel']),
    _stringValue(gpsLocation['city']),
    _stringValue(gpsNested['city']),
  ]);
  final districtLabel = _firstNonEmpty(<String>[
    explicit.districtLabel,
    _stringValue(scopeHint['districtLabel']),
    _stringValue(scopeHint['district']),
    _stringValue(gpsLocation['districtLabel']),
    _stringValue(gpsLocation['district']),
  ]);
  final countryLabel = _firstNonEmpty(<String>[
    explicit.countryLabel,
    _stringValue(scopeHint['countryLabel']),
    _stringValue(gpsLocation['countryLabel']),
  ]);
  final capturedAt = _firstNonEmpty(<String>[
    explicit.capturedAt,
    _stringValue(scopeHint['locationTimestamp']),
    _stringValue(gpsLocation['locationTimestamp']),
  ]);
  final source = _firstNonEmpty(<String>[
    explicit.source,
    _stringValue(scopeHint['geoSource']),
    if (cityLabel.isNotEmpty) 'device_location',
    if (countryCode.isNotEmpty || timezone.isNotEmpty) 'device_locale',
    'inferred',
  ]);
  final confidence = explicit.confidence > 0
      ? explicit.confidence
      : cityLabel.isNotEmpty
      ? 0.82
      : countryCode.isNotEmpty
      ? 0.68
      : 0.0;
  final privacyTier = _firstNonEmpty(<String>[
    explicit.privacyTier,
    _stringValue(scopeHint['privacyTier']),
    if (cityLabel.isNotEmpty) 'city',
    if (countryCode.isNotEmpty || regionLabel.isNotEmpty) 'region_only',
    'none',
  ]);
  return AvailableGeoContext(
    countryCode: countryCode,
    countryLabel: countryLabel,
    regionCode: regionCode,
    regionLabel: regionLabel,
    cityLabel: cityLabel,
    districtLabel: districtLabel,
    timezone: timezone,
    source: source,
    confidence: confidence,
    capturedAt: capturedAt,
    privacyTier: privacyTier,
  );
}

ResolvedGeoScope resolveGeoScope({
  required AvailableGeoContext availableGeoContext,
  ResolvedGeoScope current = const ResolvedGeoScope(),
  ResolvedGeoScope previous = const ResolvedGeoScope(),
  DefaultGeoPolicy geoPolicy = const DefaultGeoPolicy(),
}) {
  final normalizedCurrent = _normalizeResolvedGeoScope(current);
  return hasResolvedGeoScope(normalizedCurrent)
      ? normalizedCurrent
      : const ResolvedGeoScope();
}

List<String> mergeGeoAnchors(List<String> baseAnchors, ResolvedGeoScope scope) {
  return baseAnchors
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toSet()
      .toList(growable: false);
}

ResolvedGeoScope _normalizeResolvedGeoScope(ResolvedGeoScope scope) {
  return ResolvedGeoScope(
    geoKind: scope.geoKind.trim(),
    countryCode: scope.countryCode.trim().toUpperCase(),
    countryLabel: scope.countryLabel.trim(),
    regionLabel: scope.regionLabel.trim(),
    cityLabel: scope.cityLabel.trim(),
    marketCode: scope.marketCode.trim(),
    marketLabel: scope.marketLabel.trim(),
    resolvedText: scope.resolvedText.trim(),
    source: scope.source.trim(),
    defaultApplied: scope.defaultApplied,
    reason: scope.reason.trim(),
  );
}

String _countryCodeFromLocale(String raw) {
  final locale = raw.trim();
  if (locale.isEmpty) {
    return '';
  }
  final match = RegExp(r'[_-]([A-Za-z]{2})$').firstMatch(locale);
  if (match != null) {
    return (match.group(1) ?? '').trim().toUpperCase();
  }
  return '';
}

String _stringValue(Object? raw) => raw?.toString().trim() ?? '';

List<String> _stringList(Object? raw) {
  if (raw is! List) {
    return const <String>[];
  }
  return raw
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String _firstNonEmpty(List<String> values) {
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isNotEmpty) {
      return normalized;
    }
  }
  return '';
}
