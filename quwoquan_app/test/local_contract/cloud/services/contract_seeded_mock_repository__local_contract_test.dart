import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';
import '../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import '../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

void main() {
  test('alpha 测试组合根显式注入 mock repository', () {
    final container = ProviderContainer(
      overrides: [
        homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
      ],
    );
    addTearDown(container.dispose);

    expect(
      resolveAppDataSourceModeForEnvironment(
        runtimeEnv: 'alpha',
        explicitDataSource: 'remote',
      ),
      AppDataSourceMode.mock,
    );
    expect(
      container.read(homepageFacetSetProvider),
      isA<MockHomepageRepository>(),
    );
  });

  test('beta/gamma/prod 始终锁定 remote 且未知环境启动失败', () {
    for (final env in ['beta', 'gamma', 'prod']) {
      expect(
        resolveAppDataSourceModeForEnvironment(
          runtimeEnv: env,
          explicitDataSource: 'mock',
        ),
        AppDataSourceMode.remote,
      );
    }
    expect(
      () => resolveAppDataSourceModeForEnvironment(
        runtimeEnv: 'prod-sim',
        explicitDataSource: 'mock',
      ),
      throwsStateError,
    );
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

  test('content contract fixture 的核心文章保留显式创作/更新/发布时间', () async {
    final pack = loadContentScenarioPack();
    final seedSet =
        pack.seedSets['content_discovery_core'] as Map<String, dynamic>;
    final article = ((seedSet['posts'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .firstWhere((item) => item['postId'] == 'fixture_article_001');

    expect(article['createdAt'], '2026-05-01T05:00:00Z');
    expect(article['updatedAt'], '2026-05-03T05:00:00Z');
    expect(article['publishedAt'], '2026-05-02T05:00:00Z');

    final repo = buildContractSeededContentRepository(
      seedRef: 'content_discovery_core',
    );
    final detail = await repo.getPost(postId: 'fixture_article_001');

    expect(detail.post.createdAt, DateTime.utc(2026, 5, 1, 5));
    expect(detail.post.updatedAt, DateTime.utc(2026, 5, 3, 5));
    expect(detail.post.publishedAt, DateTime.utc(2026, 5, 2, 5));
    expect(detail.post.hasMeaningfulUpdate, isTrue);
    expect(detail.mergedArticleWireMap['updatedAt'], '2026-05-03T05:00:00Z');
    expect(detail.mergedArticleWireMap['publishedAt'], '2026-05-02T05:00:00Z');
  });

  test('content mock repository 默认优先读取 contract fixture', () async {
    final repo = MockContentRepository();
    final feed = await repo.listDiscoveryFeed(category: 'all');
    expect(feed.map((item) => item.id), contains('fixture_photo_001'));
  });

  test('alpha 视频播放 canary 可从默认契约 fixture 直达', () async {
    final pack = loadContentScenarioPack();
    final seedSet =
        pack.seedSets['content_discovery_core'] as Map<String, dynamic>;
    final expectedVideo = ((seedSet['posts'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .firstWhere((item) => item['postId'] == 'fixture_video_001');
    final repo = MockContentRepository();

    final detail = await repo.getPost(postId: 'fixture_video_001');

    expect(detail.post.id, 'fixture_video_001');
    expect(detail.post.mediaVideoUrl, expectedVideo['videoUrl']);
  });

  test('circle alpha query reader 可由 immutable fixture bundle 初始化', () async {
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
    final reader = AlphaCircleQueryReader();

    final circles = await reader.list(const CircleListQuery(limit: 100));
    expect(
      circles.items.map((item) => item.circleId),
      contains('fixture_circle_photo'),
    );
    expect(
      circles.items.map((item) => item.circleId),
      contains('fixture_circle_gold_invest'),
    );
    final detail = await reader.get(
      const CircleDetailQuery(circleId: 'fixture_circle_photo'),
    );
    expect(detail.name, '契约摄影社');
    final goldDetail = await reader.get(
      const CircleDetailQuery(circleId: 'fixture_circle_gold_invest'),
    );
    expect(goldDetail.name, '黄金投资圈');
  });

  test('circle alpha reader 默认优先读取 contract fixture', () async {
    final reader = AlphaCircleQueryReader();
    final circles = await reader.list(const CircleListQuery(limit: 100));
    expect(
      circles.items.map((item) => item.circleId),
      contains('fixture_circle_photo'),
    );
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
    final moneyMatches = await repo.searchHomepages(query: '钱');
    expect(
      moneyMatches.map((item) => item.id),
      contains('homepage_sight_dongqian_lake'),
    );
  });

  test('user profile mock repository 默认优先读取 contract fixture', () async {
    const repo = MockUserProfileRepository();
    final profile = await repo.getUserProfile('fixture_user_current');
    expect(profile.displayName, matches(_defaultNicknamePattern));
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
    final rawScenarios = json['scenarios'];
    final scenarios = switch (rawScenarios) {
      List<dynamic> values =>
        values
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false),
      Map<dynamic, dynamic> values =>
        values.entries
            .where((entry) => entry.value is Map)
            .map((entry) {
              final scenario = (entry.value as Map).cast<String, dynamic>();
              return <String, dynamic>{'id': entry.key.toString(), ...scenario};
            })
            .toList(growable: false),
      _ => const <Map<String, dynamic>>[],
    };
    return ContractScenarioPack(
      repositoryExpectations:
          (json['repositoryExpectations'] as Map? ?? const <String, dynamic>{})
              .map((key, value) => MapEntry(key.toString(), value.toString())),
      seedSets:
          (json['seedSets'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      scenarios: scenarios,
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
      'quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json',
    ),
  );
}

ContractScenarioPack loadCircleScenarioPack() {
  return ContractScenarioPack.fromJson(
    _loadContractFixtureObject(
      'quwoquan_service/services/circle-service/tests/support/contract_fixtures/scenarios/circle_scenarios.json',
    ),
  );
}

ContractScenarioPack loadChatScenarioPack() {
  return ContractScenarioPack.fromJson(
    _loadContractFixtureObject(
      'quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json',
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
      .map(
        (item) => contentPostDtoFromReadModelMap(item.cast<String, dynamic>()),
      )
      .toList(growable: false);
  return MockContentRepository(seedPosts: posts);
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

File? _tryContractFixtureFile(String repositoryOrMetadataPath) {
  final suffix = repositoryOrMetadataPath.startsWith('quwoquan_service/')
      ? repositoryOrMetadataPath
      : 'quwoquan_service/contracts/metadata/$repositoryOrMetadataPath';
  final candidates = <File>[
    File('../$suffix'),
    File(suffix),
    File('../../$suffix'),
  ];
  for (final candidate in candidates) {
    if (candidate.existsSync()) {
      return candidate;
    }
  }
  return null;
}
