import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

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
      'content',
      'content/test_fixtures/scenarios/content_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? circleSeedSet([String ref = 'circle_core']) {
    return _seedSet(
      'circle',
      'social/circle/test_fixtures/scenarios/circle_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? chatSeedSet([String ref = 'chat_core']) {
    return _seedSet(
      'chat',
      'messages/chat/test_fixtures/scenarios/chat_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? entitySeedSet([
    String ref = 'entity_homepage_core',
  ]) {
    return _seedSet(
      'entity',
      'entity/test_fixtures/scenarios/entity_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? userSeedSet([String ref = 'user_profile_core']) {
    return _seedSet(
      'user',
      'user/test_fixtures/scenarios/user_scenarios.json',
      ref,
    );
  }

  static Map<String, dynamic>? followingSubjectSeedSet([
    String ref = 'following_subject_core',
  ]) {
    return userSeedSet(ref);
  }

  static Map<String, dynamic>? metadataJson(String metadataRelativePath) {
    return _loadMetadataJson(metadataRelativePath);
  }

  static Map<String, dynamic>? seedManifest([
    String env = CloudRuntimeConfig.appRuntimeEnv,
  ]) {
    return _loadMetadataJson(_seedManifestPath(env), env: env);
  }

  static Map<String, dynamic>? _seedSet(
    String domain,
    String fallbackFixturePath,
    String ref,
  ) {
    final env = CloudRuntimeConfig.appRuntimeEnv;
    final fixturePath = _fixturePathForDomain(
      domain,
      fallbackFixturePath,
      env: env,
    );
    final cacheKey = '$env::$_fixtureProfile::$fixturePath::$ref';
    if (_seedCache.containsKey(cacheKey)) {
      return _seedCache[cacheKey];
    }
    Map<String, dynamic>? readSeedFromPath(String path) {
      final decoded = _loadMetadataJson(path, env: env);
      final seedSets = decoded?['seedSets'];
      if (seedSets is! Map) {
        return null;
      }
      final seed = seedSets[ref];
      if (seed is Map) {
        return seed.cast<String, dynamic>();
      }
      return null;
    }

    final seed = readSeedFromPath(fixturePath);
    if (seed != null) {
      _seedCache[cacheKey] = seed;
      return seed;
    }
    if (fixturePath != fallbackFixturePath) {
      final fallbackSeed = readSeedFromPath(fallbackFixturePath);
      if (fallbackSeed != null) {
        _seedCache[cacheKey] = fallbackSeed;
        return fallbackSeed;
      }
    }
    _seedCache[cacheKey] = null;
    return null;
  }

  static String _seedManifestPath(String env) {
    return env == 'alpha' && _fixtureProfile == 'lite'
        ? '_shared/test_fixtures/app_alpha_dev_lite_seed_manifest.json'
        : '_shared/test_fixtures/app_${env}_seed_manifest.json';
  }

  static String _fixturePathForDomain(
    String domain,
    String fallbackFixturePath, {
    String env = CloudRuntimeConfig.appRuntimeEnv,
  }) {
    final manifest = seedManifest(env);
    final entries = manifest?['seedRefs'];
    if (entries is List) {
      for (final entry in entries.whereType<Map>()) {
        final casted = entry.cast<String, dynamic>();
        if ((casted['domain'] ?? '').toString().trim() != domain) {
          continue;
        }
        final fixturePath = (casted['fixturePath'] ?? '').toString().trim();
        if (fixturePath.isNotEmpty) {
          return fixturePath;
        }
      }
    }
    return fallbackFixturePath;
  }

  static Map<String, dynamic>? _loadMetadataJson(
    String metadataRelativePath, {
    String env = CloudRuntimeConfig.appRuntimeEnv,
  }) {
    final cacheKey = '$env::$_fixtureProfile::$metadataRelativePath';
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
    final relativeCandidates = <String>[metadataRelativePath];
    final suffixes = relativeCandidates
        .map((path) => 'quwoquan_service/contracts/metadata/$path')
        .toSet()
        .toList(growable: false);
    final files = <File>[];
    final repoRoot = Platform.environment['QWQ_REPO_ROOT'];
    if (repoRoot != null && repoRoot.trim().isNotEmpty) {
      for (final suffix in suffixes) {
        files.add(File('${repoRoot.trim()}/$suffix'));
      }
    }
    for (final suffix in suffixes) {
      files.addAll(<File>[
        File('../$suffix'),
        File(suffix),
        File('../../$suffix'),
        File('../../../$suffix'),
        File('../../../../$suffix'),
      ]);
    }
    return files;
  }
}
