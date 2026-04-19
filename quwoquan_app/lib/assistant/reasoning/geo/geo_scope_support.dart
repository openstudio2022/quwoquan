import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';

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
  final raw = (retrievalPolicy['defaultGeoPolicy'] as Map?)
          ?.cast<String, dynamic>() ??
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
      context.timezone.trim().isNotEmpty ||
      context.lat.abs() > 0 ||
      context.lng.abs() > 0;
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
  final explicit =
      scopeHint['availableGeoContext'] is Map
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
  final lat = _firstNonZeroDouble(<double?>[
    explicit.lat,
    _doubleValue(scopeHint['lat']),
    _doubleValue(gpsLocation['lat']),
    _doubleValue(gpsNested['latitude']),
    _doubleValue(gpsNested['lat']),
  ]);
  final lng = _firstNonZeroDouble(<double?>[
    explicit.lng,
    _doubleValue(scopeHint['lng']),
    _doubleValue(gpsLocation['lng']),
    _doubleValue(gpsNested['longitude']),
    _doubleValue(gpsNested['lon']),
    _doubleValue(gpsNested['lng']),
  ]);
  final capturedAt = _firstNonEmpty(<String>[
    explicit.capturedAt,
    _stringValue(scopeHint['locationTimestamp']),
    _stringValue(gpsLocation['locationTimestamp']),
  ]);
  final source = _firstNonEmpty(<String>[
    explicit.source,
    _stringValue(scopeHint['geoSource']),
    if (cityLabel.isNotEmpty || lat.abs() > 0 || lng.abs() > 0) 'device_gps',
    if (countryCode.isNotEmpty || timezone.isNotEmpty) 'device_locale',
    'inferred',
  ]);
  final confidence =
      explicit.confidence > 0
          ? explicit.confidence
          : (lat.abs() > 0 || lng.abs() > 0)
          ? 0.95
          : cityLabel.isNotEmpty
          ? 0.82
          : countryCode.isNotEmpty
          ? 0.68
          : 0.0;
  final privacyTier = _firstNonEmpty(<String>[
    explicit.privacyTier,
    _stringValue(scopeHint['privacyTier']),
    if (lat.abs() > 0 || lng.abs() > 0) 'coarse_location',
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
    lat: lat,
    lng: lng,
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
  if (hasResolvedGeoScope(normalizedCurrent)) {
    return normalizedCurrent;
  }
  if (hasResolvedGeoScope(previous)) {
    final normalizedPrevious = _normalizeResolvedGeoScope(previous);
    return ResolvedGeoScope(
      geoKind: normalizedPrevious.geoKind,
      countryCode: normalizedPrevious.countryCode,
      countryLabel: normalizedPrevious.countryLabel,
      regionLabel: normalizedPrevious.regionLabel,
      cityLabel: normalizedPrevious.cityLabel,
      marketCode: normalizedPrevious.marketCode,
      marketLabel: normalizedPrevious.marketLabel,
      resolvedText: normalizedPrevious.resolvedText,
      source: normalizedPrevious.source.trim().isNotEmpty
          ? 'followup_carried'
          : normalizedPrevious.source,
      defaultApplied: normalizedPrevious.defaultApplied,
      reason: normalizedPrevious.reason.trim().isNotEmpty
          ? normalizedPrevious.reason
          : 'followup_inherit_geo',
    );
  }
  final effectiveScope = _effectiveDefaultGeoScope(
    requested: geoPolicy.defaultGeoScope,
  );
  if (!geoPolicy.fallbackAllowed || effectiveScope == 'none') {
    return const ResolvedGeoScope();
  }
  switch (effectiveScope) {
    case 'city':
      return _defaultCityScope(
        availableGeoContext: availableGeoContext,
        fallbackSources: geoPolicy.fallbackSources,
      );
    case 'market':
      return _defaultMarketScope(
        availableGeoContext: availableGeoContext,
        geoPolicy: geoPolicy,
      );
    case 'country':
      return _defaultCountryScope(availableGeoContext);
    default:
      return const ResolvedGeoScope();
  }
}

List<String> mergeGeoAnchors(
  List<String> baseAnchors,
  ResolvedGeoScope scope,
) {
  final merged = <String>{
    ...baseAnchors.map((item) => item.trim()).where((item) => item.isNotEmpty),
    ..._geoAliasTokens(scope),
  };
  return merged.toList(growable: false);
}

ResolvedGeoScope _defaultCityScope({
  required AvailableGeoContext availableGeoContext,
  required List<String> fallbackSources,
}) {
  if (availableGeoContext.cityLabel.trim().isNotEmpty) {
    return ResolvedGeoScope(
      geoKind: 'city',
      countryCode: availableGeoContext.countryCode,
      countryLabel: availableGeoContext.countryLabel,
      regionLabel: availableGeoContext.regionLabel,
      cityLabel: availableGeoContext.cityLabel,
      resolvedText: availableGeoContext.cityLabel,
      source: 'available_geo_default',
      defaultApplied: true,
      reason: 'weather_without_city_use_device_city',
    );
  }
  if (_containsSource(fallbackSources, 'available_geo.region') &&
      availableGeoContext.regionLabel.trim().isNotEmpty) {
    return ResolvedGeoScope(
      geoKind: 'region',
      countryCode: availableGeoContext.countryCode,
      countryLabel: availableGeoContext.countryLabel,
      regionLabel: availableGeoContext.regionLabel,
      resolvedText: availableGeoContext.regionLabel,
      source: 'available_geo_default',
      defaultApplied: true,
      reason: 'weather_without_city_use_region',
    );
  }
  if (_containsSource(fallbackSources, 'available_geo.country') &&
      (availableGeoContext.countryLabel.trim().isNotEmpty ||
          availableGeoContext.countryCode.trim().isNotEmpty)) {
    return _defaultCountryScope(availableGeoContext, reason: 'weather_without_city_use_country');
  }
  return const ResolvedGeoScope();
}

ResolvedGeoScope _defaultCountryScope(
  AvailableGeoContext availableGeoContext, {
  String reason = 'country_default_from_available_geo',
}) {
  final countryLabel = availableGeoContext.countryLabel.trim().isNotEmpty
      ? availableGeoContext.countryLabel.trim()
      : '';
  if (countryLabel.isEmpty && availableGeoContext.countryCode.trim().isEmpty) {
    return const ResolvedGeoScope();
  }
  return ResolvedGeoScope(
    geoKind: 'country',
    countryCode: availableGeoContext.countryCode,
    countryLabel: countryLabel,
    resolvedText: countryLabel.isNotEmpty
        ? countryLabel
        : availableGeoContext.countryCode,
    source: 'available_geo_default',
    defaultApplied: true,
    reason: reason,
  );
}

ResolvedGeoScope _defaultMarketScope({
  required AvailableGeoContext availableGeoContext,
  required DefaultGeoPolicy geoPolicy,
}) {
  final countryCode = availableGeoContext.countryCode.trim().toUpperCase();
  final countryLabel = availableGeoContext.countryLabel.trim().isNotEmpty
      ? availableGeoContext.countryLabel.trim()
      : '';
  final override = geoPolicy.marketOverrides[countryCode];
  final marketLabel = override != null && override.trim().isNotEmpty
      ? override.trim()
      : geoPolicy.marketTemplate.trim().isNotEmpty && countryLabel.isNotEmpty
      ? geoPolicy.marketTemplate.replaceAll('{countryLabel}', countryLabel)
      : '';
  if (marketLabel.isEmpty) {
    return const ResolvedGeoScope();
  }
  return ResolvedGeoScope(
    geoKind: 'market',
    countryCode: countryCode,
    countryLabel: countryLabel,
    regionLabel: availableGeoContext.regionLabel,
    marketCode: countryCode,
    marketLabel: marketLabel,
    resolvedText: marketLabel,
    source: 'available_geo_default',
    defaultApplied: true,
    reason: 'market_without_geo_use_country_market',
  );
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

String _effectiveDefaultGeoScope({
  required String requested,
}) {
  final normalized = requested.trim().toLowerCase();
  return normalized.isEmpty ? 'none' : normalized;
}

bool _containsSource(List<String> fallbackSources, String candidate) {
  if (fallbackSources.isEmpty) {
    return true;
  }
  final normalizedCandidate = candidate.trim().toLowerCase();
  return fallbackSources.any(
    (item) => item.trim().toLowerCase() == normalizedCandidate,
  );
}

List<String> _geoAliasTokens(ResolvedGeoScope scope) {
  final normalized = _normalizeResolvedGeoScope(scope);
  final tokens = <String>{
    normalized.resolvedText.trim(),
    normalized.cityLabel.trim(),
    normalized.marketLabel.trim(),
    normalized.countryLabel.trim(),
  };
  final slashSplit = normalized.resolvedText
      .split(RegExp(r'[/|｜,，]'))
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty);
  tokens.addAll(slashSplit);
  return tokens.where((item) => item.isNotEmpty).toList(growable: false);
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

double? _doubleValue(Object? raw) {
  if (raw is num) {
    return raw.toDouble();
  }
  return double.tryParse(_stringValue(raw));
}

double _firstNonZeroDouble(List<double?> values) {
  for (final value in values) {
    if (value != null && value.abs() > 0) {
      return value;
    }
  }
  return 0;
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
