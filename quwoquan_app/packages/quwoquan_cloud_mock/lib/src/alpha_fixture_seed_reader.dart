import 'dart:convert';

import 'generated/alpha_fixture_bundle.g.dart';

/// 只读取构建期固化在 [AlphaFixtureBundle] 中的不可变场景数据。
///
/// alpha adapter 与 App 测试替身共用此入口，禁止在设备运行时回读仓库相对路径。
final class AlphaFixtureSeedReader {
  AlphaFixtureSeedReader({this.bundle = alphaFixtureBundle});

  final AlphaFixtureBundle bundle;
  final Map<String, Map<String, Object?>?> _cache =
      <String, Map<String, Object?>?>{};

  Map<String, Object?>? seedSet(String domain, String ref) {
    final key = '$domain::$ref';
    if (_cache.containsKey(key)) {
      return _cache[key];
    }
    final asset = bundle.assets[domain];
    if (asset == null) {
      _cache[key] = null;
      return null;
    }
    final decoded = jsonDecode(asset.sourceJson);
    if (decoded is! Map<Object?, Object?>) {
      throw FormatException('$domain alpha fixture root must be an object');
    }
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map<Object?, Object?>) {
      throw FormatException('$domain alpha fixture seedSets must be an object');
    }
    final raw = seedSets[ref];
    if (raw == null) {
      _cache[key] = null;
      return null;
    }
    if (raw is! Map<Object?, Object?>) {
      throw FormatException('$domain/$ref alpha fixture must be an object');
    }
    final result = raw.map((key, value) => MapEntry(key.toString(), value));
    _cache[key] = result;
    return result;
  }

  Map<String, Object?> requireSeedSet(String domain, String ref) {
    final seed = seedSet(domain, ref);
    if (seed == null) {
      throw StateError('$domain/$ref alpha fixture is missing');
    }
    return seed;
  }

  Map<String, Object?>? userSeedSet([String ref = 'user_profile_core']) =>
      seedSet('user', ref);

  Map<String, Object?>? contentSeedSet([
    String ref = 'content_discovery_core',
  ]) => seedSet('content', ref);

  Map<String, Object?>? entitySeedSet([String ref = 'entity_homepage_core']) =>
      seedSet('entity', ref);
}

final AlphaFixtureSeedReader alphaFixtureSeedReader = AlphaFixtureSeedReader();
