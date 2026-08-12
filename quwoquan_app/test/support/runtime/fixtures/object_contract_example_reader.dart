import 'dart:convert';
import 'dart:io';

import 'object_contract_example_builders.dart';

/// local_contract 对象替身读取 canonical 服务场景的 runtime 窄入口。
///
/// 数据按对象测试需要从受版本控制的服务合同读取，不再生成或编译 App fixture
/// bundle；该文件只存在于 `test/support`，环境 App 与 UAT 不可达。
final class ObjectContractExampleReader {
  final Map<String, Map<String, Object?>> _documents =
      <String, Map<String, Object?>>{};
  final Map<String, Map<String, Object?>?> _examples =
      <String, Map<String, Object?>?>{};

  Map<String, Object?> document(String domain) {
    return _documents.putIfAbsent(domain, () {
      if (_builtScenarioDomains.contains(domain)) {
        return buildObjectContractExampleDocument(domain);
      }
      final sourcePath = _domainScenarioPaths[domain];
      if (sourcePath == null) {
        throw StateError('unknown local-contract scenario domain: $domain');
      }
      return _readObject(sourcePath);
    });
  }

  Map<String, Object?>? example(String domain, String ref) {
    final key = '$domain::$ref';
    if (_examples.containsKey(key)) {
      return _examples[key];
    }
    final documentRoot = document(domain);
    final examples = documentRoot['examples'];
    if (examples is! Map<Object?, Object?>) {
      throw FormatException('$domain contract examples must be an object');
    }
    final raw = examples[ref];
    if (raw == null) {
      _examples[key] = null;
      return null;
    }
    if (raw is! Map<Object?, Object?>) {
      throw FormatException('$domain/$ref scenario must be an object');
    }
    final result = raw.map((key, value) => MapEntry(key.toString(), value));
    _examples[key] = result;
    return result;
  }

  Map<String, Object?> requireExample(String domain, String ref) {
    final value = example(domain, ref);
    if (value == null) {
      throw StateError('$domain/$ref local-contract scenario is missing');
    }
    return value;
  }

  Map<String, Object?>? userExample([String ref = 'user_profile_core']) =>
      example('user', ref);

  Map<String, Object?>? contentExample([
    String ref = 'content_discovery_core',
  ]) => example('content', ref);

  Map<String, Object?>? entityExample([String ref = 'entity_homepage_core']) =>
      example('entity', ref);

  Map<String, Object?> releaseObject(String repositoryRelativePath) =>
      _readObject(repositoryRelativePath);
}

final ObjectContractExampleReader objectContractExampleReader =
    ObjectContractExampleReader();

const Map<String, String> _domainScenarioPaths = <String, String>{
  'entity':
      'quwoquan_service/services/entity-service/tests/support/contract_examples/entity_homepage_examples.json',
  'integration':
      'quwoquan_service/services/integration-service/tests/support/contract_fixtures/scenarios/integration_scenarios.json',
  'notification':
      'quwoquan_service/services/notification-service/tests/support/contract_fixtures/scenarios/notification_scenarios.json',
  'rtc':
      'quwoquan_service/services/rtc-service/tests/support/contract_fixtures/scenarios/rtc_scenarios.json',
  'search':
      'quwoquan_service/services/search-service/tests/support/contract_fixtures/scenarios/search_scenarios.json',
};

const Set<String> _builtScenarioDomains = <String>{
  'chat',
  'circle',
  'content',
  'tag',
  'user',
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
