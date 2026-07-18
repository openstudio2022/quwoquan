part of 'circle_repository.dart';

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

class MockCircleRepository implements CircleRepository {
  MockCircleRepository({List<CircleDto>? seedCircles})
    : _circles =
          seedCircles ?? CircleContractSeedHelpers.repositorySeedCircles();

  final List<CircleDto> _circles;

  List<CircleDto> _copyCircleDtos() {
    return List<CircleDto>.from(_circles, growable: false);
  }

  CircleDto? _findCircle(String circleId) {
    for (final c in _circles) {
      if (c.id == circleId) return c;
    }
    return null;
  }

  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  }) async {
    var result = _copyCircleDtos();
    if (category != null) {
      result = result
          .where((c) => c.category == category)
          .toList(growable: false);
    }
    if (subCategory != null) {
      result = result
          .where((c) => c.subCategory == subCategory)
          .toList(growable: false);
    }
    if (domainId != null) {
      result = result
          .where((c) => c.domainId == domainId)
          .toList(growable: false);
    }
    return result.take(limit).toList(growable: false);
  }

  @override
  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const CircleSearchResultView();
    }
    final filtered = _copyCircleDtos()
        .where((circle) {
          if (categoryId != null &&
              categoryId.isNotEmpty &&
              circle.category != categoryId) {
            return false;
          }
          if (subCategory != null &&
              subCategory.isNotEmpty &&
              circle.subCategory != subCategory) {
            return false;
          }
          final name = circle.name.toLowerCase();
          final description = (circle.description ?? '').toLowerCase();
          return name.contains(normalizedQuery) ||
              description.contains(normalizedQuery);
        })
        .toList(growable: false);
    final items = filtered
        .take(limit)
        .map((circle) {
          final name = circle.name;
          return CircleSearchItemView.fromMap(<String, dynamic>{
            ...circle.toMap(),
            'categoryId': circle.category,
            'circleId': circle.id,
            'highlightText': name,
            'matchedField': 'name',
          });
        })
        .toList(growable: false);
    final facetCounts = <String, int>{};
    for (final circle in filtered) {
      final key = (circle.subCategory ?? circle.category ?? '').trim();
      if (key.isEmpty) {
        continue;
      }
      facetCounts.update(key, (value) => value + 1, ifAbsent: () => 1);
    }
    final facetBuckets = filtered
        .map(
          (circle) => <String, dynamic>{
            'facetKey': (circle.subCategory ?? circle.category ?? '')
                .toString(),
            'label': (circle.subCategory ?? circle.category ?? '').toString(),
            'categoryId': circle.category,
            'subCategory': circle.subCategory,
          },
        )
        .where((facet) => (facet['facetKey'] ?? '').toString().isNotEmpty)
        .fold<Map<String, Map<String, dynamic>>>(
          <String, Map<String, dynamic>>{},
          (accumulator, facet) {
            accumulator.putIfAbsent(
              facet['facetKey']!.toString(),
              () => <String, dynamic>{
                ...facet,
                'facetCount': facetCounts[facet['facetKey']] ?? 0,
              },
            );
            return accumulator;
          },
        )
        .values
        .map(CircleFacetBucketView.fromMap)
        .toList(growable: false);
    return CircleSearchResultView(items: items, facetBuckets: facetBuckets);
  }

  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    final match = _findCircle(circleId);
    if (match == null) {
      throw CloudErrorMapper.fromStatusCode(
        404,
        body:
            '{"code":"${CircleErrorCode.circleNotFound.code}","userMessage":"${CircleErrorMessages.zh[CircleErrorCode.circleNotFound]}"}',
        requestPath: CircleApiMetadata.getCirclePath(circleId: circleId),
      );
    }
    return CircleDetailPayload.fromWire(_mockCircleDetailWireFromDto(match));
  }

  @override
  Future<CircleDto> createCircle(CircleCreateWireDto data) async {
    final merge = data.toMockMergeMap();
    final circleId = (merge['id']?.toString().trim().isNotEmpty ?? false)
        ? merge['id'].toString().trim()
        : 'local_${DateTime.now().millisecondsSinceEpoch}';
    final created = CircleContractSeedHelpers.normalizedCircle(
      merge,
      circleId: circleId,
    );
    final dto = CircleDto.fromMap(created);
    _circles.removeWhere((circle) => circle.id == circleId);
    _circles.insert(0, dto);
    return dto;
  }

  @override
  Future<CircleDto> updateCircle(
    String circleId,
    CircleUpdateWireDto data,
  ) async {
    final existing = (await getCircle(circleId)).repositoryMergeBase();
    final updatedAt = DateTime.now().toIso8601String();
    final merged = CircleContractSeedHelpers.normalizedCircle(
      <String, dynamic>{...existing, ...data.toMap(), 'updatedAt': updatedAt},
      circleId: circleId,
      fallbackUpdatedAt: updatedAt,
    );
    final dto = CircleDto.fromMap(merged);
    final index = _circles.indexWhere((circle) => circle.id == circleId);
    if (index >= 0) {
      _circles[index] = dto;
    } else {
      _circles.insert(0, dto);
    }
    return dto;
  }

  @override
  Future<void> archiveCircle(String circleId) async {}

  @override
  Future<List<PostBaseDto>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  }) async {
    final normalizedType = _normalizeCircleFeedType(type);
    final source = CircleContractSeedHelpers.circleFeedRows(circleId);
    final maps = source
        .where((item) {
          if (identity != null && identity.isNotEmpty) {
            if ((item['contentIdentity'] ?? '').toString() != identity) {
              return false;
            }
          }
          if (normalizedType != null && normalizedType.isNotEmpty) {
            final itemType = _normalizeCircleFeedType(
              item['contentType']?.toString(),
            );
            return itemType == normalizedType;
          }
          return true;
        })
        .take(limit)
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    return maps.map(contentPostDtoFromReadModelMap).toList(growable: false);
  }

  @override
  Future<CircleStatsWireDto> getCircleStats(String circleId) async {
    final contractStats = CircleContractSeedHelpers.statsForCircle(circleId);
    if (contractStats != null) {
      final memberCount = CircleContractSeedHelpers.intValue(
        contractStats['memberCount'],
      );
      final postCount = CircleContractSeedHelpers.intValue(
        contractStats['postCount'],
      );
      final weeklyActive = CircleContractSeedHelpers.intValue(
        contractStats['weeklyActiveCount'],
      );
      final discussionCount = CircleContractSeedHelpers.intValue(
        contractStats['discussionCount'],
      );
      return CircleStatsWireDto.fromMap(<String, dynamic>{
        'circleId': circleId,
        'memberCount': memberCount,
        'postCount': postCount,
        'discussionCount': discussionCount,
        'weeklyActiveCount': weeklyActive,
        'likeCount': 0,
      });
    }
    final circle = _findCircle(circleId);
    if (circle != null) {
      return CircleStatsWireDto.fromMap(<String, dynamic>{
        'circleId': circleId,
        'memberCount': circle.memberCount,
        'postCount': circle.postCount,
        'discussionCount': 0,
        'weeklyActiveCount': circle.weeklyActiveCount,
        'likeCount': 0,
      });
    }
    return CircleStatsWireDto.fromMap(<String, dynamic>{
      'circleId': circleId,
      'memberCount': 0,
      'postCount': 0,
      'discussionCount': 0,
      'weeklyActiveCount': 0,
      'likeCount': 0,
    });
  }

  /// 圈子影响样本视觉（统一交互子契约 · 传播节点）；asset 路径，非外链。
  static final List<IntersectionVisual>
  _circleImpactSampleVisuals = <IntersectionVisual>[
    IntersectionVisual(
      assetKind: 'avatar',
      imageUrl:
          'media/avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png',
      displayName: '林清越',
      target: IntersectionTarget(
        objectId: 'fixture_user_lin',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
    ),
    IntersectionVisual(
      assetKind: 'avatar',
      imageUrl:
          'media/avatar/s/archived-avatar/user/fixture_user_travel/v1/avatar.png',
      displayName: '周屿',
      target: IntersectionTarget(
        objectId: 'fixture_user_zhou',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
    ),
  ];

  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    final stats = (await getCircleStats(circleId)).raw;
    final memberCount = CircleContractSeedHelpers.intValue(
      stats['memberCount'],
    );
    final postCount = CircleContractSeedHelpers.intValue(stats['postCount']);
    final weeklyActive = CircleContractSeedHelpers.intValue(
      stats['weeklyActiveCount'],
    );
    return CircleImpactSummary(
      circleId: circleId,
      total: memberCount + postCount + weeklyActive,
      items: <CircleImpactItem>[
        if (memberCount > 0)
          CircleImpactItem(
            helpType: 'relationship',
            action: 'establish_connection',
            intersectionDimension: 'relationship',
            source: 'circle_members',
            count: memberCount,
            primaryText: '$memberCount人在这里建立了新连接',
            subtitleText: '你认识的人也在这里',
            iconKey: 'connect',
            impactId: 'circle_${circleId}_relationship',
            primarySpans: <IntersectionTextSpan>[
              IntersectionTextSpan(text: '$memberCount', role: 'count'),
              IntersectionTextSpan(text: '人在这里建立了新连接', role: 'plain'),
            ],
            sampleVisuals: _circleImpactSampleVisuals,
            propagationPath: IntersectionPropagationPath(
              pathKind: 'personToPerson',
              hopCount: 1,
              secondarySpreadCount: memberCount > 6 ? 4 : 1,
              summaryText: '你认识的人也在这里',
              nodes: _circleImpactSampleVisuals,
            ),
          ),
        if (postCount > 0)
          CircleImpactItem(
            helpType: 'community',
            action: 'start_discussion',
            intersectionDimension: 'content',
            source: 'circle_posts',
            count: postCount,
            primaryText: '$postCount个讨论正在这里发生',
            iconKey: 'discussion',
            impactId: 'circle_${circleId}_community',
            primarySpans: <IntersectionTextSpan>[
              IntersectionTextSpan(text: '$postCount', role: 'count'),
              IntersectionTextSpan(text: '个讨论正在这里发生', role: 'plain'),
            ],
          ),
        if (weeklyActive > 0)
          CircleImpactItem(
            helpType: 'spread',
            action: 'active_participation',
            intersectionDimension: 'interest',
            source: 'circle_weekly_active',
            count: weeklyActive,
            primaryText: '$weeklyActive人最近参与了这里',
            iconKey: 'people',
            impactId: 'circle_${circleId}_spread',
            primarySpans: <IntersectionTextSpan>[
              IntersectionTextSpan(text: '$weeklyActive', role: 'count'),
              IntersectionTextSpan(text: '人最近参与了这里', role: 'plain'),
            ],
          ),
      ],
    );
  }

  @override
  Future<void> updateSections(
    String circleId,
    List<CircleSectionConfigDto> sections,
  ) async {}

  @override
  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    final contractRows = CircleContractSeedHelpers.homeFeedRows();
    if (contractRows.isNotEmpty) {
      return contractRows
          .take(limit)
          .map(
            (row) =>
                contentPostDtoFromReadModelMap(Map<String, dynamic>.from(row)),
          )
          .toList(growable: false);
    }
    return CircleMockData.catalogCircleFeedPostDtos
        .take(limit)
        .toList(growable: false);
  }

  @override
  List<CircleDto> publishFlowRecommendedCircles() {
    final now = DateTime.now().toUtc();
    return <CircleDto>[
      CircleDto(
        id: 'rec-city',
        name: '城市探索',
        coverUrl:
            'media/image/s/mock/seed/p_1500530855697-b586d89ba3ee/v1/image.jpg',
        ownerId: 'embedded_owner',
        memberCount: 890,
        postCount: 126,
        createdAt: now,
        updatedAt: now,
      ),
      CircleDto(
        id: 'rec-run',
        name: '跑步日记',
        coverUrl:
            'media/image/s/mock/seed/p_1486218119243-13883505764c/v1/image.jpg',
        ownerId: 'embedded_owner',
        memberCount: 312,
        postCount: 58,
        createdAt: now,
        updatedAt: now,
      ),
    ];
  }

  @override
  Future<Map<String, CircleCategoryTabConfigDto>>
  getCircleCategoryConfig() async {
    return Map<String, CircleCategoryTabConfigDto>.from(
      CircleCategoryTabDefaults.remoteStyleFallback,
    );
  }
}
