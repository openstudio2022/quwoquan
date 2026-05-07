import 'dart:convert';
import 'dart:io';

/// 本地/测试态 contract fixture 加载器。
///
/// 生产包不会挂载 `contracts/metadata/**/test_fixtures`，因此移动端运行时通常
/// 找不到这些文件并自动回退既有数据。alpha 本地开发与自动化测试在仓库根目录
/// 可见时，MockRepository 默认从同一套端云契约 seed 初始化。
class ContractFixtureRuntimeLoader {
  ContractFixtureRuntimeLoader._();

  static const String _fixtureProfile = String.fromEnvironment(
    'CONTRACT_FIXTURE_PROFILE',
    defaultValue: 'lite',
  );

  static final Map<String, Map<String, dynamic>?> _metadataCache =
      <String, Map<String, dynamic>?>{};
  static final Map<String, Map<String, dynamic>?> _seedCache =
      <String, Map<String, dynamic>?>{};

  static Map<String, dynamic>? contentSeedSet([
    String ref = 'content_discovery_core',
  ]) {
    return _seedSet(
      'content/test_fixtures/scenarios/content_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? circleSeedSet([String ref = 'circle_core']) {
    return _seedSet(
      'social/circle/test_fixtures/scenarios/circle_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? chatSeedSet([String ref = 'chat_core']) {
    return _seedSet(
      'messages/chat/test_fixtures/scenarios/chat_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? entitySeedSet([
    String ref = 'entity_homepage_core',
  ]) {
    return _seedSet(
      'entity/test_fixtures/scenarios/entity_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? userSeedSet([String ref = 'user_profile_core']) {
    return _seedSet('user/test_fixtures/scenarios/user_scenarios.json', ref);
  }

  static Map<String, dynamic>? seedManifest([String env = 'alpha']) {
    final preferredPath =
        env == 'alpha' && _fixtureProfile == 'lite'
        ? '_shared/test_fixtures/app_alpha_dev_lite_seed_manifest.json'
        : '_shared/test_fixtures/app_${env}_seed_manifest.json';
    return _loadMetadataJson(preferredPath);
  }

  static Map<String, dynamic>? _seedSet(String fixturePath, String ref) {
    final cacheKey = '$_fixtureProfile::$fixturePath::$ref';
    if (_seedCache.containsKey(cacheKey)) {
      return _seedCache[cacheKey];
    }
    final decoded = _loadMetadataJson(fixturePath);
    final seedSets = decoded?['seedSets'];
    if (seedSets is! Map) {
      _seedCache[cacheKey] = null;
      return null;
    }
    final seed = seedSets[ref];
    if (seed is Map) {
      final casted = seed.cast<String, dynamic>();
      _seedCache[cacheKey] = casted;
      return casted;
    }
    _seedCache[cacheKey] = null;
    return null;
  }

  static Map<String, dynamic>? _loadMetadataJson(String metadataRelativePath) {
    final cacheKey = '$_fixtureProfile::$metadataRelativePath';
    if (_metadataCache.containsKey(cacheKey)) {
      return _metadataCache[cacheKey];
    }
    for (final file in _candidateFiles(metadataRelativePath)) {
      try {
        if (!file.existsSync()) {
          continue;
        }
        final decoded = jsonDecode(file.readAsStringSync());
        if (decoded is Map) {
          final casted = decoded.cast<String, dynamic>();
          _metadataCache[cacheKey] = casted;
          return casted;
        }
      } catch (_) {
        continue;
      }
    }
    _metadataCache[cacheKey] = null;
    return null;
  }

  static List<File> _candidateFiles(String metadataRelativePath) {
    final relativeCandidates = <String>[
      ..._profileAwarePaths(metadataRelativePath),
      metadataRelativePath,
    ];
    final suffixes = relativeCandidates
        .map((path) => 'quwoquan_service/contracts/metadata/$path')
        .toSet()
        .toList(growable: false);
    final files = <File>[];
    for (final suffix in suffixes) {
      files.addAll(<File>[
        File('../$suffix'),
        File(suffix),
        File('../../$suffix'),
        File('../../../$suffix'),
        File('../../../../$suffix'),
        File('/Users/zhaoyuxi/Projects/quwoquan/$suffix'),
      ]);
    }
    return files;
  }

  static List<String> _profileAwarePaths(String metadataRelativePath) {
    if (_fixtureProfile != 'lite') {
      return const <String>[];
    }
    if (metadataRelativePath.endsWith('_seed_manifest.json')) {
      return const <String>[];
    }
    if (!metadataRelativePath.endsWith('.json')) {
      return const <String>[];
    }
    return <String>[
      metadataRelativePath.replaceFirst('.json', '.lite.json'),
    ];
  }
}
