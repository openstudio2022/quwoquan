part of 'entity_repository.dart';

abstract class HomepageIntroductionRepository {
  Future<HomepageIntroduction?> getHomepageIntroduction(String homepageId);
}

class MockHomepageIntroductionRepository
    implements HomepageIntroductionRepository {
  const MockHomepageIntroductionRepository();

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId,
  ) async {
    final resolvedHomepage = MockHomepageRepository()._findHomepage(homepageId);
    final resolvedHomepageId = resolvedHomepage?.id ?? homepageId;
    final seed = ContractFixtureRuntimeLoader.entitySeedSet();
    final homepages = seed?['homepages'];
    if (homepages is List) {
      for (final raw in homepages) {
        if (raw is! Map) {
          continue;
        }
        final map = raw.cast<String, dynamic>();
        final id = (map['homepageId'] ?? map['id'] ?? '').toString();
        if (id != resolvedHomepageId) {
          continue;
        }
        final intro = map['introduction'];
        if (intro is Map<String, dynamic>) {
          return HomepageIntroduction.fromMap(intro);
        }
        if (intro is Map) {
          return HomepageIntroduction.fromMap(Map<String, dynamic>.from(intro));
        }
      }
    }
    final homepage = resolvedHomepage;
    if (homepage == null) {
      return null;
    }
    return _fallbackIntroductionFromHomepage(homepage);
  }
}

class RemoteHomepageIntroductionRepository
    implements HomepageIntroductionRepository {
  RemoteHomepageIntroductionRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId,
  ) async {
    final decoded = await _httpClient.getJson(
      _uri(
        EntityApiMetadata.getHomepageIntroductionPath(homepageId: homepageId),
      ),
      headers: CloudRequestHeaders.forSurfaceOperation(
        surfaceId: AppUiSurfaces.homepageIntroduction.id,
        routeId: AppUiSurfaces.homepageIntroduction.routeId,
        operationId: EntityApiMetadata.getHomepageIntroductionOperation,
        clientPageId: EntityRequestPageIds.getHomepageIntroduction,
      ),
    );
    final object = CloudResponseDecoder.asObject(
      decoded,
      context: CloudRequestHeaders.contextForSurfaceOperation(
        surfaceId: AppUiSurfaces.homepageIntroduction.id,
        operationId: EntityApiMetadata.getHomepageIntroductionOperation,
      ),
    );
    if (object.isEmpty) {
      return null;
    }
    return HomepageIntroduction.fromMap(object);
  }
}

HomepageIntroduction _fallbackIntroductionFromHomepage(
  HomepageDetail homepage,
) {
  final summaryParts = <String>[
    if ((homepage.subtitle ?? '').trim().isNotEmpty) homepage.subtitle!.trim(),
    if (homepage.categoryTags.isNotEmpty)
      homepage.categoryTags.take(3).join('、'),
    if ((homepage.city ?? '').trim().isNotEmpty) homepage.city!.trim(),
  ];
  final summary = summaryParts.isEmpty
      ? '${homepage.title} 的基础信息、内容和讨论正在持续整理中。'
      : summaryParts.join(' · ');
  return HomepageIntroduction(
    homepageId: homepage.id,
    displayName: homepage.title,
    homepageType: homepage.homepageType,
    coverUrl: homepage.coverUrl,
    summary: summary,
    sections: <HomepageIntroductionSection>[
      HomepageIntroductionSection(
        kind: 'overview',
        title: '概况',
        bodyMarkdown:
            '$summary\n\n这个页面用于长期整理与 ${homepage.title} 相关的基础信息、内容、讨论和兴趣圈。随着更多真实内容与来源进入，介绍页会继续补充时间线、关键事实与相关对象。',
      ),
      HomepageIntroductionSection(
        kind: 'keyFacts',
        title: '核心信息',
        bodyMarkdown: <String>[
          '- 类型：${homepage.homepageType}',
          if ((homepage.city ?? '').trim().isNotEmpty)
            '- 所在城市：${homepage.city}',
          if (homepage.categoryTags.isNotEmpty)
            '- 关键词：${homepage.categoryTags.join('、')}',
        ].join('\n'),
      ),
    ],
    relatedObjects: homepage.relatedGroups,
    updatedAt: homepage.updatedAt?.toUtc().toIso8601String() ?? '',
  );
}
