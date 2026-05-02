import 'dart:convert';
import 'dart:io';

/// 本地/测试态 contract fixture 加载器。
///
/// 生产包不会挂载 `contracts/metadata/**/test_fixtures`，因此移动端运行时通常
/// 找不到这些文件并自动回退既有数据。alpha 本地开发与自动化测试在仓库根目录
/// 可见时，MockRepository 默认从同一套端云契约 seed 初始化。
class ContractFixtureRuntimeLoader {
  ContractFixtureRuntimeLoader._();

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
    return _loadMetadataJson(
      '_shared/test_fixtures/app_${env}_seed_manifest.json',
    );
  }

  static Map<String, dynamic>? _seedSet(String fixturePath, String ref) {
    final decoded = _loadMetadataJson(fixturePath);
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

  static Map<String, dynamic>? _loadMetadataJson(String metadataRelativePath) {
    for (final file in _candidateFiles(metadataRelativePath)) {
      try {
        if (!file.existsSync()) {
          continue;
        }
        final decoded = jsonDecode(file.readAsStringSync());
        if (decoded is Map) {
          return decoded.cast<String, dynamic>();
        }
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  static List<File> _candidateFiles(String metadataRelativePath) {
    final suffix = 'quwoquan_service/contracts/metadata/$metadataRelativePath';
    return <File>[
      File('../$suffix'),
      File(suffix),
      File('../../$suffix'),
      File('../../../$suffix'),
      File('../../../../$suffix'),
      File('/Users/zhaoyuxi/Projects/quwoquan/$suffix'),
    ];
  }
}
