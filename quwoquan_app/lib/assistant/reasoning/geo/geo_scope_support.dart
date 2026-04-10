import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';

class DefaultGeoPolicy {
  const DefaultGeoPolicy({
    this.defaultGeoScope = 'none',
    this.fallbackAllowed = false,
    this.fallbackSources = const <String>[],
    this.marketTemplate = '',
    this.marketOverrides = const <String, String>{},
    this.scopeCatalog = const <GeoScopeCatalogEntry>[],
  });

  final String defaultGeoScope;
  final bool fallbackAllowed;
  final List<String> fallbackSources;
  final String marketTemplate;
  final Map<String, String> marketOverrides;
  final List<GeoScopeCatalogEntry> scopeCatalog;
}

class GeoScopeCatalogEntry {
  const GeoScopeCatalogEntry({
    this.geoKind = '',
    this.countryCode = '',
    this.countryLabel = '',
    this.regionLabel = '',
    this.cityLabel = '',
    this.marketCode = '',
    this.marketLabel = '',
    this.resolvedText = '',
    this.aliases = const <String>[],
    this.reason = 'user_explicit_scope',
  });

  final String geoKind;
  final String countryCode;
  final String countryLabel;
  final String regionLabel;
  final String cityLabel;
  final String marketCode;
  final String marketLabel;
  final String resolvedText;
  final List<String> aliases;
  final String reason;
}

DefaultGeoPolicy parseDefaultGeoPolicy(Map<String, dynamic> retrievalPolicy) {
  final raw = (retrievalPolicy['defaultGeoPolicy'] as Map?)
          ?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final overrides = <String, String>{};
  final rawOverrides =
      (raw['marketOverrides'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
  final scopeCatalog =
      (raw['scopeCatalog'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .map(
            (item) => GeoScopeCatalogEntry(
              geoKind: _stringValue(item['geoKind']).toLowerCase(),
              countryCode: _stringValue(item['countryCode']).toUpperCase(),
              countryLabel: _stringValue(item['countryLabel']),
              regionLabel: _stringValue(item['regionLabel']),
              cityLabel: _stringValue(item['cityLabel']),
              marketCode: _stringValue(item['marketCode']),
              marketLabel: _stringValue(item['marketLabel']),
              resolvedText: _stringValue(item['resolvedText']),
              aliases: _stringList(item['aliases']),
              reason: _stringValue(item['reason']).isNotEmpty
                  ? _stringValue(item['reason'])
                  : 'user_explicit_scope',
            ),
          )
          .where((item) => item.aliases.isNotEmpty)
          .toList(growable: false) ??
      const <GeoScopeCatalogEntry>[];
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
    scopeCatalog: scopeCatalog,
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
  required String userQuery,
  required String domainId,
  required AvailableGeoContext availableGeoContext,
  ResolvedGeoScope current = const ResolvedGeoScope(),
  ResolvedGeoScope previous = const ResolvedGeoScope(),
  DefaultGeoPolicy geoPolicy = const DefaultGeoPolicy(),
}) {
  final explicit = _extractExplicitGeoScope(
    userQuery,
    geoPolicy: geoPolicy,
  );
  if (hasResolvedGeoScope(explicit)) {
    return explicit;
  }
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

String applyResolvedGeoToQuery(String query, ResolvedGeoScope scope) {
  final base = _compressWhitespace(query);
  if (base.isEmpty) {
    return base;
  }
  final normalizedScope = _normalizeResolvedGeoScope(scope);
  if (!hasResolvedGeoScope(normalizedScope)) {
    return base;
  }
  final resolvedText = normalizedScope.resolvedText.trim();
  if (resolvedText.isEmpty) {
    return base;
  }
  final existing = _normalizedToken(base);
  for (final token in _geoAliasTokens(normalizedScope)) {
    if (token.isEmpty) {
      continue;
    }
    if (existing.contains(_normalizedToken(token))) {
      return base;
    }
  }
  final leadingRange = RegExp(
    r'^(\d{4}-\d{2}-\d{2}(?:\s+至\s+\d{4}-\d{2}-\d{2})?)\s+(.+)$',
  ).firstMatch(base);
  if (leadingRange != null) {
    final rangeText = (leadingRange.group(1) ?? '').trim();
    final remainder = (leadingRange.group(2) ?? '').trim();
    if (rangeText.isNotEmpty && remainder.isNotEmpty) {
      return _compressWhitespace('$rangeText $resolvedText $remainder');
    }
  }
  return _compressWhitespace('$resolvedText $base');
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

ResolvedGeoScope _extractExplicitGeoScope(
  String query, {
  required DefaultGeoPolicy geoPolicy,
}) {
  final configuredScope = _extractConfiguredScope(query, geoPolicy.scopeCatalog);
  if (hasResolvedGeoScope(configuredScope)) {
    return configuredScope;
  }
  final explicitCity = _extractExplicitCity(query);
  if (hasResolvedGeoScope(explicitCity)) {
    return explicitCity;
  }
  return const ResolvedGeoScope();
}

ResolvedGeoScope _extractConfiguredScope(
  String query,
  List<GeoScopeCatalogEntry> catalog,
) {
  final normalized = query.trim();
  if (normalized.isEmpty || catalog.isEmpty) {
    return const ResolvedGeoScope();
  }
  final haystack = _normalizedToken(normalized);
  for (final entry in catalog) {
    for (final alias in entry.aliases) {
      final token = _normalizedToken(alias);
      if (token.isEmpty || !haystack.contains(token)) {
        continue;
      }
      final resolvedText = _resolvedTextFromCatalogEntry(entry);
      if (resolvedText.isEmpty) {
        continue;
      }
      return ResolvedGeoScope(
        geoKind: entry.geoKind.trim().isNotEmpty ? entry.geoKind.trim() : 'none',
        countryCode: entry.countryCode.trim().toUpperCase(),
        countryLabel: entry.countryLabel.trim(),
        regionLabel: entry.regionLabel.trim(),
        cityLabel: entry.cityLabel.trim(),
        marketCode: entry.marketCode.trim(),
        marketLabel: entry.marketLabel.trim(),
        resolvedText: resolvedText,
        source: 'user_explicit',
        reason: entry.reason.trim().isNotEmpty
            ? entry.reason.trim()
            : 'user_explicit_scope',
      );
    }
  }
  return const ResolvedGeoScope();
}

String _resolvedTextFromCatalogEntry(GeoScopeCatalogEntry entry) {
  final candidates = <String>[
    entry.resolvedText.trim(),
    entry.marketLabel.trim(),
    entry.cityLabel.trim(),
    entry.regionLabel.trim(),
    entry.countryLabel.trim(),
    entry.countryCode.trim().toUpperCase(),
  ];
  for (final candidate in candidates) {
    if (candidate.isNotEmpty) {
      return candidate;
    }
  }
  return '';
}

ResolvedGeoScope _extractExplicitCity(String query) {
  final city = _extractCityCandidate(query);
  if (city.isEmpty) {
    return const ResolvedGeoScope();
  }
  return ResolvedGeoScope(
    geoKind: 'city',
    cityLabel: city,
    resolvedText: city,
    source: 'user_explicit',
    reason: 'user_explicit_city',
  );
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
  final marketLabel = scope.marketLabel.trim();
  final cityLabel = scope.cityLabel.trim();
  final countryLabel = scope.countryLabel.trim();
  final resolvedText = scope.resolvedText.trim().isNotEmpty
      ? scope.resolvedText.trim()
      : marketLabel.isNotEmpty
      ? marketLabel
      : cityLabel.isNotEmpty
      ? cityLabel
      : countryLabel;
  final geoKind = scope.geoKind.trim().isNotEmpty
      ? scope.geoKind.trim()
      : marketLabel.isNotEmpty
      ? 'market'
      : cityLabel.isNotEmpty
      ? 'city'
      : countryLabel.isNotEmpty
      ? 'country'
      : 'none';
  return ResolvedGeoScope(
    geoKind: geoKind,
    countryCode: scope.countryCode.trim().toUpperCase(),
    countryLabel: countryLabel,
    regionLabel: scope.regionLabel.trim(),
    cityLabel: cityLabel,
    marketCode: scope.marketCode.trim(),
    marketLabel: marketLabel,
    resolvedText: resolvedText,
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

String _extractCityCandidate(String text) {
  if (text.trim().isEmpty) {
    return '';
  }
  final placeLikeMatches = RegExp(
    r'([\u4e00-\u9fffA-Za-z]{2,20}(?:市|区|县|镇|乡|村|街道|公园|景区|机场|车站|大厦|广场|口岸|山|湖|河|沟|湾|岛|草原))',
  ).allMatches(text);
  for (final match in placeLikeMatches) {
    final normalized = _normalizeLocationCandidate(match.group(1));
    if (normalized.isNotEmpty) {
      return normalized;
    }
  }
  final weatherPrefix = RegExp(
    r'([\u4e00-\u9fffA-Za-z]{2,12})(?:天气|气温|温度|下雨|降雨|穿什么|带外套)',
  ).firstMatch(text);
  if (weatherPrefix != null) {
    final normalized = _normalizeLocationCandidate(weatherPrefix.group(1));
    if (normalized.isNotEmpty) {
      return normalized;
    }
  }
  final connectorMatch = RegExp(
    r'(?:在|去|到|从|围绕|关于|针对)\s*([\u4e00-\u9fffA-Za-z]{2,16})',
  ).firstMatch(text);
  if (connectorMatch != null) {
    return _normalizeLocationCandidate(connectorMatch.group(1));
  }
  return '';
}

String _normalizeLocationCandidate(String? raw) {
  final candidate = (raw ?? '')
      .trim()
      .replaceFirst(
        RegExp(r'^(如果把|如果将|把|将|往|向|到|在|去|从|围绕|关于|针对)'),
        '',
      )
      .replaceFirst(
        RegExp(r'(今天|明天|后天|前天|昨日|昨天|今日|今晚|今早|本周|这周|下周|上周|周[一二三四五六日天末])+$'),
        '',
      )
      .replaceFirst(RegExp(r'(呢|呀|啊|吗|吧|吗？|\?)$'), '')
      .trim();
  if (candidate.length < 2 || candidate.length > 20) {
    return '';
  }
  const blocked = <String>{
    '今天',
    '明天',
    '后天',
    '现在',
    '当前',
    '最近',
    '这里',
    '那里',
    '这个',
    '那个',
    '问题',
    '方案',
    '情况',
    '东西',
    '资料',
  };
  if (blocked.contains(candidate)) {
    return '';
  }
  if (RegExp(r'^(今天|明天|后天|这周|下周|周末|最近|当前|现在)').hasMatch(candidate)) {
    return '';
  }
  return candidate;
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

String _compressWhitespace(String raw) {
  return raw.replaceAll(RegExp(r'\s+'), ' ').trim();
}

String _normalizedToken(String raw) {
  return raw
      .replaceAll(RegExp(r'[\s:：|｜/、,，。！？!?._-]+'), '')
      .toLowerCase();
}
