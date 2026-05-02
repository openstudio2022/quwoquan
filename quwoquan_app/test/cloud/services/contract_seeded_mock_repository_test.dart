import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  test('alpha 环境契约要求端侧使用 mock repository', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    expect(CloudRuntimeConfig.appRuntimeEnv, 'alpha');
    expect(container.read(appDataSourceModeProvider), AppDataSourceMode.mock);
  });

  test('content mock repository 可由 contracts fixture 初始化', () async {
    final pack = loadContentScenarioPack();
    final seedRefs = pack.seedRefsFor('content_discovery_feed_basic');
    expect(
      seedRefs,
      containsAll([
        'content_discovery_core',
        'home_feed_core',
        'content_detail_core',
        'search_core',
        'publish_core',
      ]),
    );
    final repo = buildContractSeededContentRepository(
      seedRef: 'content_discovery_core',
    );

    final photoItems = await repo.listDiscoveryFeed(
      category: 'photo',
      identity: 'work',
      type: 'photo',
    );
    expect(photoItems.map((item) => item.id), contains('fixture_photo_001'));

    final articles = await repo.listDiscoveryFeed(
      category: 'article',
      identity: 'work',
      type: 'article',
    );
    expect(articles.map((item) => item.id), contains('fixture_article_001'));
  });

  test('content mock repository 默认优先读取 contract fixture', () async {
    final repo = MockContentRepository();
    final feed = await repo.listDiscoveryFeed(category: 'all');
    expect(feed.map((item) => item.id), contains('fixture_photo_001'));
  });

  test('circle mock repository 可由 contracts fixture 初始化', () async {
    final pack = loadCircleScenarioPack();
    final seedRefs = pack.seedRefsFor('circle_list_detail_basic');
    expect(
      seedRefs,
      containsAll([
        'circle_core',
        'circle_home_feed_core',
        'circle_profile_core',
        'circle_group_chat_link_core',
      ]),
    );
    final repo = buildContractSeededCircleRepository(seedRef: 'circle_core');

    final circles = await repo.listCircles();
    expect(circles.map((item) => item.id), contains('fixture_circle_photo'));
    final detail = await repo.getCircle('fixture_circle_photo');
    expect(detail.circle.name, '契约摄影社');
  });

  test('circle mock repository 默认优先读取 contract fixture', () async {
    final repo = MockCircleRepository();
    final circles = await repo.listCircles();
    expect(circles.map((item) => item.id), contains('fixture_circle_photo'));
  });

  test('chat mock repository 可由 contracts fixture 初始化', () async {
    final pack = loadChatScenarioPack();
    final seedRefs = pack.seedRefsFor('chat_inbox_detail_basic');
    expect(
      seedRefs,
      containsAll([
        'chat_core',
        'chat_settings_core',
        'chat_contacts_core',
        'chat_group_flow_core',
      ]),
    );
    final repo = buildContractSeededChatRepository(seedRef: 'chat_core');

    final inbox = await repo.listInbox();
    expect(inbox.map((item) => item.id), contains('fixture_conv_direct'));
    final messages = await repo.listMessages(
      conversationId: 'fixture_conv_direct',
    );
    expect(messages.map((item) => item.content), contains('这是一条契约聊天消息。'));
    final members = await repo.listMembers(
      conversationId: 'fixture_conv_direct',
    );
    expect(members.map((item) => item.userId), contains('fixture_user_friend'));
  });

  test('chat mock repository 默认优先读取 contract fixture', () async {
    final repo = MockChatRepository();
    final inbox = await repo.listInbox();
    expect(inbox.map((item) => item.id), contains('fixture_conv_direct'));
  });

  test('homepage mock repository 默认优先读取 contract fixture', () async {
    final repo = MockHomepageRepository();
    final items = await repo.searchHomepages(query: '契约');
    expect(items.map((item) => item.id), contains('fixture_homepage_author'));
  });

  test('app content mock repository 默认优先读取 contract fixture', () {
    final repo = MockAppContentRepository();
    expect(
      repo.discoveryPhotoData.map((item) => item.id),
      contains('fixture_photo_001'),
    );
    expect(
      repo.discoveryArticleData.map((item) => item.id),
      contains('fixture_article_001'),
    );
  });

  test('user profile mock repository 默认优先读取 contract fixture', () async {
    const repo = MockUserProfileRepository();
    final profile = await repo.getUserProfile('fixture_user_current');
    expect(profile.displayName, '契约当前用户');
    final relationship = await repo.getRelationship('fixture_user_photo');
    expect(relationship.isMutual, isTrue);
  });

  test('app alpha/beta/gamma seed manifests 引用的 fixture seedRefs 均存在', () {
    for (final env in ['alpha', 'beta', 'gamma']) {
      final manifest = loadSeedManifest(env);
      expect(manifest.environment, env);
      for (final item in manifest.seedRefs) {
        final fixture = loadScenarioPackByPath(item.fixturePath);
        for (final ref in item.refs) {
          expect(
            fixture.seedSets,
            contains(ref),
            reason: '${item.fixturePath} should contain $ref',
          );
        }
      }
    }
  });
}

class ContractScenarioPack {
  const ContractScenarioPack({
    required this.repositoryExpectations,
    required this.seedSets,
    required this.scenarios,
  });

  final Map<String, String> repositoryExpectations;
  final Map<String, dynamic> seedSets;
  final List<Map<String, dynamic>> scenarios;

  factory ContractScenarioPack.fromJson(Map<String, dynamic> json) {
    return ContractScenarioPack(
      repositoryExpectations:
          (json['repositoryExpectations'] as Map? ?? const <String, dynamic>{})
              .map((key, value) => MapEntry(key.toString(), value.toString())),
      seedSets:
          (json['seedSets'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      scenarios: ((json['scenarios'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false),
    );
  }

  List<String> seedRefsFor(String scenarioId) {
    final scenario = scenarios.firstWhere(
      (item) => item['id'] == scenarioId,
      orElse: () => const <String, dynamic>{},
    );
    return ((scenario['seedRefs'] as List?) ?? const <dynamic>[])
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
}

class SeedManifest {
  const SeedManifest({required this.environment, required this.seedRefs});

  final String environment;
  final List<SeedManifestEntry> seedRefs;

  factory SeedManifest.fromJson(Map<String, dynamic> json) {
    return SeedManifest(
      environment: json['environment'].toString(),
      seedRefs: ((json['seedRefs'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map(
            (item) => SeedManifestEntry.fromJson(item.cast<String, dynamic>()),
          )
          .toList(growable: false),
    );
  }
}

class SeedManifestEntry {
  const SeedManifestEntry({
    required this.domain,
    required this.fixturePath,
    required this.refs,
  });

  final String domain;
  final String fixturePath;
  final List<String> refs;

  factory SeedManifestEntry.fromJson(Map<String, dynamic> json) {
    return SeedManifestEntry(
      domain: json['domain'].toString(),
      fixturePath: json['fixturePath'].toString(),
      refs: ((json['refs'] as List?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(growable: false),
    );
  }
}

ContractScenarioPack loadContentScenarioPack() {
  return ContractScenarioPack.fromJson(
    _loadContractFixtureObject(
      'content/test_fixtures/scenarios/content_scenarios.json',
    ),
  );
}

ContractScenarioPack loadCircleScenarioPack() {
  return ContractScenarioPack.fromJson(
    _loadContractFixtureObject(
      'social/circle/test_fixtures/scenarios/circle_scenarios.json',
    ),
  );
}

ContractScenarioPack loadChatScenarioPack() {
  return ContractScenarioPack.fromJson(
    _loadContractFixtureObject(
      'messages/chat/test_fixtures/scenarios/chat_scenarios.json',
    ),
  );
}

SeedManifest loadSeedManifest(String env) {
  return SeedManifest.fromJson(
    _loadContractFixtureObject(
      '_shared/test_fixtures/app_${env}_seed_manifest.json',
    ),
  );
}

ContractScenarioPack loadScenarioPackByPath(String metadataRelativePath) {
  return ContractScenarioPack.fromJson(
    _loadContractFixtureObject(metadataRelativePath),
  );
}

MockContentRepository buildContractSeededContentRepository({
  String seedRef = 'content_discovery_core',
}) {
  final pack = loadContentScenarioPack();
  final seedSet = pack.seedSets[seedRef] as Map<String, dynamic>;
  final posts = ((seedSet['posts'] as List?) ?? const <dynamic>[])
      .whereType<Map>()
      .map((item) => postBaseDtoFromMap(item.cast<String, dynamic>()))
      .toList(growable: false);
  return MockContentRepository(seedPosts: posts);
}

MockCircleRepository buildContractSeededCircleRepository({
  String seedRef = 'circle_core',
}) {
  final pack = loadCircleScenarioPack();
  final seedSet = pack.seedSets[seedRef] as Map<String, dynamic>;
  final circles = ((seedSet['circles'] as List?) ?? const <dynamic>[])
      .whereType<Map>()
      .map((item) => CircleDto.fromMap(item.cast<String, dynamic>()))
      .toList(growable: false);
  return MockCircleRepository(seedCircles: circles);
}

MockChatRepository buildContractSeededChatRepository({
  String seedRef = 'chat_core',
}) {
  final pack = loadChatScenarioPack();
  final seedSet = pack.seedSets[seedRef] as Map<String, dynamic>;
  final conversations =
      ((seedSet['conversations'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
  final members = _mapOfList(seedSet['members']);
  final messages = _mapOfList(seedSet['messages']);
  return MockChatRepository(
    seedConversations: conversations,
    seedMembers: members,
    seedMessages: messages,
  );
}

Map<String, List<Map<String, dynamic>>> _mapOfList(Object? value) {
  return ((value as Map?) ?? const <String, dynamic>{}).map(
    (key, raw) => MapEntry(
      key.toString(),
      ((raw as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false),
    ),
  );
}

Map<String, dynamic> _loadContractFixtureObject(String metadataRelativePath) {
  final file = _tryContractFixtureFile(metadataRelativePath);
  if (file == null) {
    throw StateError(
      'contract fixture 缺失: $metadataRelativePath, cwd=${Directory.current.path}',
    );
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

File? _tryContractFixtureFile(String metadataRelativePath) {
  final candidates = <File>[
    File('../quwoquan_service/contracts/metadata/$metadataRelativePath'),
    File('quwoquan_service/contracts/metadata/$metadataRelativePath'),
    File('../../quwoquan_service/contracts/metadata/$metadataRelativePath'),
  ];
  for (final candidate in candidates) {
    if (candidate.existsSync()) {
      return candidate;
    }
  }
  return null;
}
