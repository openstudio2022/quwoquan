import 'dart:convert';

final class GammaHomepageUatCase {
  const GammaHomepageUatCase({
    required this.entityRef,
    required this.homepageId,
    required this.title,
  });

  final String entityRef;
  final String homepageId;
  final String title;
}

List<GammaHomepageUatCase> parseGammaHomepageUatCases(String encodedPayload) {
  if (encodedPayload.isEmpty) {
    throw StateError('missing release-bound Gamma homepage UAT cases');
  }
  final Object decoded;
  try {
    decoded = jsonDecode(utf8.decode(base64.decode(encodedPayload)));
  } on FormatException catch (error) {
    throw StateError(
      'invalid release-bound Gamma homepage UAT case encoding: $error',
    );
  }
  if (decoded is! Map<Object?, Object?>) {
    throw StateError('Gamma homepage UAT cases must be an object');
  }
  const rootKeys = <String>{
    'schema',
    'environment',
    'releaseId',
    'runId',
    'importerReportRef',
    'generatedAt',
    'cases',
  };
  final root = <String, Object?>{};
  for (final entry in decoded.entries) {
    if (entry.key is! String) {
      throw StateError('Gamma homepage UAT cases contain a non-string key');
    }
    root[entry.key as String] = entry.value;
  }
  if (!_hasExactKeys(root.keys, rootKeys) ||
      root['schema'] != 'quwoquan_data.homepage_verification_case_manifest' ||
      root['environment'] != 'gamma') {
    throw StateError('Gamma homepage UAT manifest contract mismatch');
  }
  for (final key in <String>[
    'releaseId',
    'runId',
    'importerReportRef',
    'generatedAt',
  ]) {
    if (root[key] is! String || (root[key] as String).trim().isEmpty) {
      throw StateError('Gamma homepage UAT manifest $key is invalid');
    }
  }
  final rawCases = root['cases'];
  if (rawCases is! List<Object?> || rawCases.isEmpty) {
    throw StateError('Gamma homepage UAT manifest has no cases');
  }
  final entityRefs = <String>{};
  final homepageIds = <String>{};
  final cases = <GammaHomepageUatCase>[];
  for (final rawCase in rawCases) {
    if (rawCase is! Map<Object?, Object?>) {
      throw StateError('Gamma homepage UAT case must be an object');
    }
    final row = <String, Object?>{};
    for (final entry in rawCase.entries) {
      if (entry.key is! String) {
        throw StateError('Gamma homepage UAT case contains a non-string key');
      }
      row[entry.key as String] = entry.value;
    }
    if (!_hasExactKeys(row.keys, const <String>{
      'entityRef',
      'homepageId',
      'title',
    })) {
      throw StateError('Gamma homepage UAT case contract mismatch');
    }
    final entityRef = _requiredText(row, 'entityRef');
    final homepageId = _requiredText(row, 'homepageId');
    final title = _requiredText(row, 'title');
    if (!entityRefs.add(entityRef) || !homepageIds.add(homepageId)) {
      throw StateError('Gamma homepage UAT case identity is duplicated');
    }
    cases.add(
      GammaHomepageUatCase(
        entityRef: entityRef,
        homepageId: homepageId,
        title: title,
      ),
    );
  }
  return cases;
}

bool _hasExactKeys(Iterable<String> actual, Set<String> expected) {
  final keys = actual.toSet();
  return keys.length == expected.length && keys.containsAll(expected);
}

String _requiredText(Map<String, Object?> row, String key) {
  final value = row[key];
  if (value is! String || value.trim().isEmpty) {
    throw StateError('Gamma homepage UAT case $key is invalid');
  }
  return value.trim();
}
