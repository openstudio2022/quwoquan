import 'dart:convert';
import 'dart:io';

/// local_contract 对象替身读取 canonical 服务场景的 runtime 窄入口。
///
/// 数据按对象测试需要从受版本控制的服务合同读取，不再生成或编译 App fixture
/// bundle；该文件只存在于 `test/support`，环境 App 与 UAT 不可达。
final class ObjectScenarioSeedReader {
  final Map<String, Map<String, Object?>> _documents =
      <String, Map<String, Object?>>{};
  final Map<String, Map<String, Object?>?> _seeds =
      <String, Map<String, Object?>?>{};

  Map<String, Object?> document(String domain) {
    return _documents.putIfAbsent(domain, () {
      final sourcePath = _domainScenarioPaths[domain];
      if (sourcePath == null) {
        throw StateError('unknown local-contract scenario domain: $domain');
      }
      return _readObject(sourcePath);
    });
  }

  Map<String, Object?>? seedSet(String domain, String ref) {
    final key = '$domain::$ref';
    if (_seeds.containsKey(key)) {
      return _seeds[key];
    }
    final seedSets = document(domain)['seedSets'];
    if (seedSets is! Map<Object?, Object?>) {
      throw FormatException('$domain scenario seedSets must be an object');
    }
    final raw = seedSets[ref];
    if (raw == null) {
      _seeds[key] = null;
      return null;
    }
    if (raw is! Map<Object?, Object?>) {
      throw FormatException('$domain/$ref scenario must be an object');
    }
    final result = raw.map((key, value) => MapEntry(key.toString(), value));
    _seeds[key] = result;
    return result;
  }

  Map<String, Object?> requireSeedSet(String domain, String ref) {
    final seed = seedSet(domain, ref);
    if (seed == null) {
      throw StateError('$domain/$ref local-contract scenario is missing');
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

  Map<String, Object?> releaseObject(String repositoryRelativePath) =>
      _readObject(repositoryRelativePath);
}

final ObjectScenarioSeedReader objectScenarioSeedReader =
    ObjectScenarioSeedReader();

const Map<String, String> _domainScenarioPaths = <String, String>{
  'assistant':
      'quwoquan_service/services/assistant-service/tests/support/contract_fixtures/scenarios/assistant_scenarios.json',
  'chat':
      'quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json',
  'circle':
      'quwoquan_service/services/circle-service/tests/support/contract_fixtures/scenarios/circle_scenarios.json',
  'content':
      'quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json',
  'entity':
      'quwoquan_service/services/entity-service/tests/support/contract_fixtures/scenarios/entity_scenarios.json',
  'integration':
      'quwoquan_service/services/integration-service/tests/support/contract_fixtures/scenarios/integration_scenarios.json',
  'notification':
      'quwoquan_service/services/notification-service/tests/support/contract_fixtures/scenarios/notification_scenarios.json',
  'rtc':
      'quwoquan_service/services/rtc-service/tests/support/contract_fixtures/scenarios/rtc_scenarios.json',
  'search':
      'quwoquan_service/services/search-service/tests/support/contract_fixtures/scenarios/search_scenarios.json',
  'tag':
      'quwoquan_service/services/tag-service/tests/support/contract_fixtures/scenarios/tag_scenarios.json',
  'user':
      'quwoquan_service/services/user-service/tests/support/contract_fixtures/scenarios/user_scenarios.json',
};

Map<String, Object?> _readObject(String repositoryRelativePath) {
  final candidates = <File>[
    File(repositoryRelativePath),
    File('../$repositoryRelativePath'),
    File('../../$repositoryRelativePath'),
  ];
  final source = candidates
      .where((candidate) => candidate.existsSync())
      .firstOrNull;
  if (source == null) {
    throw StateError(
      'local-contract scenario is missing: $repositoryRelativePath '
      '(cwd=${Directory.current.path})',
    );
  }
  final decoded = jsonDecode(source.readAsStringSync());
  if (decoded is! Map<Object?, Object?>) {
    throw FormatException('$repositoryRelativePath must contain a JSON object');
  }
  return decoded.map((key, value) => MapEntry(key.toString(), value));
}
