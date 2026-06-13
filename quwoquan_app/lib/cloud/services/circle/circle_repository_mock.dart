part of 'circle_repository.dart';

/// Mock 详情 wire：在 [CircleDto.toMap] 上补齐 UI/Mock 仍消费的别名键与主圈视角字段。
Map<String, dynamic> _mockCircleDetailWireFromDto(CircleDto d) {
  final w = Map<String, dynamic>.from(d.toMap());
  final contractRow = CircleContractSeedHelpers.circleRowById(d.id);
  w['categoryId'] = d.category;
  final cover = (d.coverUrl ?? '').trim();
  if (cover.isNotEmpty) {
    w['cover'] = cover;
    w['avatar'] = cover;
    w['avatarUrl'] = cover;
  }
  if (d.description != null && d.description!.isNotEmpty) {
    w['desc'] = d.description;
  }
  if (contractRow != null) {
    final role = (contractRow['role'] ?? '').toString().trim();
    final joinStatus = (contractRow['joinStatus'] ?? '').toString().trim();
    if (role.isNotEmpty) {
      w['role'] = role;
    }
    if (joinStatus.isNotEmpty) {
      w['joinStatus'] = joinStatus;
    }
    if (contractRow['isFollowed'] is bool) {
      w['isFollowed'] = contractRow['isFollowed'] as bool;
    }
  } else {
    w.putIfAbsent('role', () => 'member');
    w.putIfAbsent('joinStatus', () => 'none');
    w.putIfAbsent('isFollowed', () => false);
  }
  final sectionConfig = w['sectionConfig'];
  if (sectionConfig is! List || sectionConfig.isEmpty) {
    w['sectionConfig'] = const <Map<String, dynamic>>[
      {'sectionType': 'works', 'visible': true, 'order': 0},
      {'sectionType': 'interaction', 'visible': true, 'order': 1},
      {'sectionType': 'chat', 'visible': true, 'order': 2},
      {'sectionType': 'storage', 'visible': true, 'order': 3},
    ];
  }
  w.putIfAbsent('storageUsedBytes', () => 0);
  w.putIfAbsent('storageQuotaBytes', () => 1073741824);
  w.putIfAbsent('autoSyncChat', () => true);
  return w;
}

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

class MockCircleRepository implements CircleRepository {
  MockCircleRepository({List<CircleDto>? seedCircles})
    : _circles =
          seedCircles ?? CircleContractSeedHelpers.repositorySeedCircles();

  final List<CircleDto> _circles;
  final Map<String, List<CircleGroupDto>> _groupCache = {};
  final Map<String, List<CircleGroupMemberDto>> _groupMembersCache = {};

  List<CircleDto> _copyCircleDtos() {
    return List<CircleDto>.from(_circles, growable: false);
  }

  CircleDto? _findCircle(String circleId) {
    for (final c in _circles) {
      if (c.id == circleId) return c;
    }
    return null;
  }

  List<CircleGroupDto> _ensureGroupCache(String circleId) {
    final existing = _groupCache[circleId];
    if (existing != null) {
      return existing;
    }
    final contractGroups = CircleContractSeedHelpers.groupsForCircle(circleId);
    if (contractGroups.isNotEmpty) {
      final now = DateTime.now().toIso8601String();
      final groups = <CircleGroupDto>[];
      for (var i = 0; i < contractGroups.length; i++) {
        final raw = contractGroups[i];
        final groupId =
            (raw['_id'] ?? raw['id'] ?? '${circleId}_group_contract_$i')
                .toString();
        groups.add(
          CircleGroupDto.fromMap(
            CircleContractSeedHelpers.normalizedCircleGroup(
              raw,
              circleId: circleId,
              groupId: groupId,
              fallbackUpdatedAt: now,
            ),
          ),
        );
      }
      _groupCache[circleId] = groups;
      return groups;
    }
    final circle = _findCircle(circleId);
    if (circle == null) {
      _groupCache[circleId] = <CircleGroupDto>[];
      return _groupCache[circleId]!;
    }
    final now = DateTime.now().toIso8601String();
    final circleName = circle.name.trim().isEmpty ? '讨论' : circle.name.trim();
    final description = (circle.description ?? '').trim();
    final ownerUserId = circle.ownerId.trim().isEmpty
        ? 'owner_user'
        : circle.ownerId.trim();
    final groups = <CircleGroupDto>[
      CircleGroupDto.fromMap(
        CircleContractSeedHelpers.normalizedCircleGroup(
          <String, dynamic>{
            'name': '$circleName主群',
            'description': description.isEmpty
                ? '默认公共群'
                : '$description · 默认公共群',
            'groupType': 'public_group',
            'visibility': 'public',
            'joinPolicy': 'apply_only',
            'ownerUserId': ownerUserId,
            'memberCount': circle.memberCount,
            'conversationId': 'conv_${circleId}_group_default',
            'isDefaultPublicGroup': true,
            'lastActiveAt': circle.updatedAt.toIso8601String(),
          },
          circleId: circleId,
          groupId: '${circleId}_group_default',
          fallbackUpdatedAt: now,
        ),
      ),
    ];
    final displaySubjectType = circle.displaySubjectType.trim();
    if (displaySubjectType != 'circle') {
      groups.add(
        CircleGroupDto.fromMap(
          CircleContractSeedHelpers.normalizedCircleGroup(
            <String, dynamic>{
              'name': circleName,
              'description': description,
              'groupType': 'org_node',
              'nodeType': 'generic',
              'visibility': 'public',
              'joinPolicy': 'apply_only',
              'ownerUserId': ownerUserId,
              'memberCount': circle.memberCount,
              'lastActiveAt': circle.updatedAt.toIso8601String(),
            },
            circleId: circleId,
            groupId: '${circleId}_node_root',
            fallbackUpdatedAt: now,
          ),
        ),
      );
    }
    _groupCache[circleId] = groups;
    return groups;
  }

  List<CircleGroupMemberDto> _ensureGroupMembersCache(
    String circleId,
    String groupId,
  ) {
    final key = '$circleId::$groupId';
    final existing = _groupMembersCache[key];
    if (existing != null) {
      return existing;
    }
    final contractGroupIds = CircleContractSeedHelpers.groupsForCircle(
      circleId,
    ).map((item) => (item['_id'] ?? item['id'] ?? '').toString()).toSet();
    final contractMembers = CircleContractSeedHelpers.membersForCircle(
      circleId,
    );
    if (contractMembers.isNotEmpty && contractGroupIds.contains(groupId)) {
      final now = DateTime.now().toIso8601String();
      final members = <CircleGroupMemberDto>[];
      for (var i = 0; i < contractMembers.length; i++) {
        final raw = contractMembers[i];
        final userId = (raw['userId'] ?? '').toString();
        final joinedAt = (raw['joinedAt'] ?? now).toString();
        final updatedAt = (raw['lastActiveAt'] ?? raw['updatedAt'] ?? joinedAt)
            .toString();
        final memberId = (raw['_id'] ?? raw['id'] ?? '${groupId}_${userId}_$i')
            .toString();
        members.add(
          CircleGroupMemberDto.fromMap(<String, dynamic>{
            ...raw,
            '_id': memberId,
            'id': memberId,
            'groupId': groupId,
            'circleId': circleId,
            'role': (raw['role'] ?? 'member').toString(),
            'status': (raw['status'] ?? 'joined').toString(),
            'joinedAt': joinedAt,
            'createdAt': raw['createdAt'] ?? joinedAt,
            'updatedAt': updatedAt,
          }),
        );
      }
      _groupMembersCache[key] = members;
      return members;
    }
    CircleGroupDto? group;
    for (final g in _ensureGroupCache(circleId)) {
      if (g.id == groupId) {
        group = g;
        break;
      }
    }
    if (group == null) {
      _groupMembersCache[key] = <CircleGroupMemberDto>[];
      return _groupMembersCache[key]!;
    }
    final ownerUserId = group.ownerUserId.trim().isEmpty
        ? 'owner_user'
        : group.ownerUserId.trim();
    final now = DateTime.now().toIso8601String();
    final members = <CircleGroupMemberDto>[
      CircleGroupMemberDto.fromMap(<String, dynamic>{
        '_id': '${groupId}_$ownerUserId',
        'id': '${groupId}_$ownerUserId',
        'groupId': groupId,
        'circleId': circleId,
        'userId': ownerUserId,
        'role': 'owner',
        'status': 'joined',
        'joinedAt': now,
        'createdAt': now,
        'updatedAt': now,
      }),
    ];
    _groupMembersCache[key] = members;
    return members;
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
      return Future.error(Exception('Circle $circleId not found'));
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
  Future<void> joinCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {}

  @override
  Future<void> leaveCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {}

  @override
  Future<List<CircleMemberRosterItemDto>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractMembers = CircleContractSeedHelpers.membersForCircle(
      circleId,
    );
    if (contractMembers.isNotEmpty) {
      return contractMembers
          .take(limit)
          .map(
            (m) => CircleMemberRosterItemDto.fromMap(
              Map<String, dynamic>.from(m),
              circleId: circleId,
            ),
          )
          .toList(growable: false);
    }
    return const <CircleMemberRosterItemDto>[];
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {}

  @override
  Future<List<CircleGroupDto>> listCircleGroups(
    String circleId, {
    String? groupType,
    String? visibility,
    String? parentGroupId,
    String? nodeType,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var groups = _ensureGroupCache(circleId);
    if (groupType != null && groupType.isNotEmpty) {
      groups = groups
          .where((g) => g.groupType == groupType)
          .toList(growable: false);
    }
    if (visibility != null && visibility.isNotEmpty) {
      groups = groups
          .where((g) => g.visibility == visibility)
          .toList(growable: false);
    }
    if (parentGroupId != null && parentGroupId.isNotEmpty) {
      groups = groups
          .where((g) => g.parentGroupId == parentGroupId)
          .toList(growable: false);
    }
    if (nodeType != null && nodeType.isNotEmpty) {
      groups = groups
          .where((g) => g.nodeType == nodeType)
          .toList(growable: false);
    }
    return groups.take(limit).toList(growable: false);
  }

  @override
  Future<List<CircleGroupDto>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <CircleGroupDto>[];
    }
    final groups = await listCircleGroups(
      circleId,
      groupType: groupType,
      visibility: visibility,
      limit: 100,
    );
    return groups
        .where((group) {
          final name = group.name.toLowerCase();
          final description = (group.description ?? '').toLowerCase();
          return name.contains(normalizedQuery) ||
              description.contains(normalizedQuery);
        })
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<CircleGroupDto> getCircleGroup(String circleId, String groupId) async {
    for (final g in _ensureGroupCache(circleId)) {
      if (g.id == groupId) return g;
    }
    return Future.error(Exception('Circle group $groupId not found'));
  }

  @override
  Future<CircleGroupDto> createCircleGroup(
    String circleId,
    CircleGroupCreateWireDto data,
  ) async {
    final d = data.toMap();
    final now = DateTime.now().toIso8601String();
    final groupId = (d['id']?.toString().trim().isNotEmpty ?? false)
        ? d['id'].toString().trim()
        : 'local_group_${DateTime.now().millisecondsSinceEpoch}';
    final groupWire = CircleContractSeedHelpers.normalizedCircleGroup(
      <String, dynamic>{...d, 'createdAt': now, 'updatedAt': now},
      circleId: circleId,
      groupId: groupId,
      fallbackUpdatedAt: now,
    );
    final group = CircleGroupDto.fromMap(groupWire);
    final groups = _ensureGroupCache(circleId);
    groups.removeWhere((g) => g.id == groupId);
    groups.insert(0, group);
    final ownerId = group.ownerUserId;
    _groupMembersCache['$circleId::$groupId'] = <CircleGroupMemberDto>[
      CircleGroupMemberDto.fromMap(<String, dynamic>{
        '_id': '${groupId}_$ownerId',
        'id': '${groupId}_$ownerId',
        'groupId': groupId,
        'circleId': circleId,
        'userId': ownerId,
        'role': 'owner',
        'status': 'joined',
        'joinedAt': now,
        'createdAt': now,
        'updatedAt': now,
      }),
    ];
    return group;
  }

  @override
  Future<CircleGroupDto> updateCircleGroup(
    String circleId,
    String groupId,
    CircleGroupUpdateWireDto data,
  ) async {
    final existing = (await getCircleGroup(circleId, groupId)).toMap();
    final now = DateTime.now().toIso8601String();
    final mergedWire = CircleContractSeedHelpers.normalizedCircleGroup(
      <String, dynamic>{...existing, ...data.toMap(), 'updatedAt': now},
      circleId: circleId,
      groupId: groupId,
      fallbackUpdatedAt: now,
    );
    final merged = CircleGroupDto.fromMap(mergedWire);
    final groups = _ensureGroupCache(circleId);
    final index = groups.indexWhere((g) => g.id == groupId);
    if (index >= 0) {
      groups[index] = merged;
    } else {
      groups.insert(0, merged);
    }
    return merged;
  }

  @override
  Future<void> applyJoinCircleGroup(String circleId, String groupId) async {
    const currentUserId = 'current_user';
    final members = _ensureGroupMembersCache(circleId, groupId);
    final now = DateTime.now().toIso8601String();
    final index = members.indexWhere((m) => m.userId == currentUserId);
    final pendingWire = <String, dynamic>{
      '_id': '${groupId}_$currentUserId',
      'id': '${groupId}_$currentUserId',
      'groupId': groupId,
      'circleId': circleId,
      'userId': currentUserId,
      'role': 'member',
      'status': 'pending',
      'createdAt': now,
      'updatedAt': now,
    };
    if (index >= 0) {
      members[index] = CircleGroupMemberDto.fromMap(<String, dynamic>{
        ...members[index].toMap(),
        ...pendingWire,
      });
    } else {
      members.add(CircleGroupMemberDto.fromMap(pendingWire));
    }
  }

  @override
  Future<List<CircleGroupMemberDto>> listCircleGroupMembers(
    String circleId,
    String groupId, {
    String? status,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var members = _ensureGroupMembersCache(circleId, groupId);
    if (status != null && status.isNotEmpty) {
      members = members
          .where((m) => m.status == status)
          .toList(growable: false);
    }
    return members.take(limit).toList(growable: false);
  }

  @override
  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final members = _ensureGroupMembersCache(circleId, groupId);
    final index = members.indexWhere((m) => m.userId == userId);
    if (index < 0) {
      return;
    }
    final now = DateTime.now().toIso8601String();
    final prev = members[index];
    final wasJoined = prev.status == 'joined';
    members[index] = CircleGroupMemberDto.fromMap(<String, dynamic>{
      ...prev.toMap(),
      'status': 'joined',
      'joinedAt': prev.joinedAt?.toIso8601String() ?? now,
      'decidedAt': now,
      'updatedAt': now,
    });
    if (wasJoined) {
      return;
    }
    final groups = _ensureGroupCache(circleId);
    final groupIndex = groups.indexWhere((g) => g.id == groupId);
    if (groupIndex >= 0) {
      final g = groups[groupIndex];
      groups[groupIndex] = CircleGroupDto.fromMap(
        CircleContractSeedHelpers.normalizedCircleGroup(
          <String, dynamic>{
            ...g.toMap(),
            'memberCount': g.memberCount + 1,
            'lastActiveAt': now,
            'updatedAt': now,
          },
          circleId: circleId,
          groupId: groupId,
          fallbackUpdatedAt: now,
        ),
      );
    }
  }

  @override
  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final members = _ensureGroupMembersCache(circleId, groupId);
    final index = members.indexWhere((m) => m.userId == userId);
    if (index < 0) {
      return;
    }
    final now = DateTime.now().toIso8601String();
    final prev = members[index];
    members[index] = CircleGroupMemberDto.fromMap(<String, dynamic>{
      ...prev.toMap(),
      'status': 'rejected',
      'decidedAt': now,
      'updatedAt': now,
    });
  }

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
        .where((item) => item['circleId'] == circleId)
        .where((item) {
          if (identity != null && identity.isNotEmpty) {
            if ((item['contentIdentity'] ?? '').toString() != identity) {
              return false;
            }
          }
          if (normalizedType != null && normalizedType.isNotEmpty) {
            final itemType = _normalizeCircleFeedType(
              item['contentType']?.toString() ?? item['type']?.toString(),
            );
            return itemType == normalizedType;
          }
          return true;
        })
        .take(limit)
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    return _decodeCircleFeedMaps(maps);
  }

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {}

  @override
  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  }) async {}

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
      return CircleStatsWireDto.fromMap(<String, dynamic>{
        'circleId': circleId,
        'members': memberCount,
        'totalMembers': memberCount,
        'posts': postCount,
        'totalPosts': postCount,
        'weeklyActive': weeklyActive,
        'active': weeklyActive,
        'likes': 0,
        'totalLikes': 0,
      });
    }
    final circle = _findCircle(circleId);
    if (circle != null) {
      return CircleStatsWireDto.fromMap(<String, dynamic>{
        'circleId': circleId,
        'members': circle.memberCount,
        'totalMembers': circle.memberCount,
        'posts': circle.postCount,
        'totalPosts': circle.postCount,
        'weeklyActive': circle.weeklyActiveCount,
        'active': circle.weeklyActiveCount,
        'likes': 0,
        'totalLikes': 0,
      });
    }
    return CircleStatsWireDto.fromMap(<String, dynamic>{
      'circleId': circleId,
      'members': 0,
      'totalMembers': 0,
      'posts': 0,
      'totalPosts': 0,
      'weeklyActive': 0,
      'active': 0,
      'likes': 0,
      'totalLikes': 0,
    });
  }

  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    final stats = (await getCircleStats(circleId)).raw;
    final memberCount = CircleContractSeedHelpers.intValue(
      stats['totalMembers'] ?? stats['members'],
    );
    final postCount = CircleContractSeedHelpers.intValue(
      stats['totalPosts'] ?? stats['posts'],
    );
    final weeklyActive = CircleContractSeedHelpers.intValue(
      stats['weeklyActive'] ?? stats['active'],
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
            displayText: '$memberCount人在这里建立了新连接',
          ),
        if (postCount > 0)
          CircleImpactItem(
            helpType: 'community',
            action: 'start_discussion',
            intersectionDimension: 'content',
            source: 'circle_posts',
            count: postCount,
            displayText: '$postCount个讨论正在这里发生',
          ),
        if (weeklyActive > 0)
          CircleImpactItem(
            helpType: 'spread',
            action: 'active_participation',
            intersectionDimension: 'interest',
            source: 'circle_weekly_active',
            count: weeklyActive,
            displayText: '$weeklyActive人最近参与了这里',
          ),
      ],
    );
  }

  @override
  Future<List<CircleFileDto>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var result = CircleContractSeedHelpers.filesForCircle(circleId);
    if (parentId != null) {
      result = result
          .where((f) => f['parentId'] == parentId)
          .toList(growable: false);
    }
    return result
        .take(limit)
        .map(
          (f) => CircleFileDto.fromMap({
            ...Map<String, dynamic>.from(f),
            'circleId': circleId,
          }),
        )
        .toList(growable: false);
  }

  @override
  Future<CircleFileDto> createFile(
    String circleId,
    CircleFileCreateWireDto data,
  ) async {
    final now = DateTime.now().toIso8601String();
    final d = data.toMap();
    final wire = <String, dynamic>{
      ...d,
      'id': 'f_${DateTime.now().millisecondsSinceEpoch}',
      'circleId': circleId,
      'createdAt': now,
      'updatedAt': now,
      'uploaderId': (d['uploaderId'] ?? 'u1').toString(),
      'status': (d['status'] ?? 'active').toString(),
      'sizeBytes': (d['sizeBytes'] as num?)?.toInt() ?? 0,
      'name': (d['name'] ?? '').toString(),
      'fileType': (d['fileType'] ?? 'file').toString(),
    };
    return CircleFileDto.fromMap(wire);
  }

  @override
  Future<CircleFileDto> getFile(String circleId, String fileId) async {
    final contractFiles = CircleContractSeedHelpers.filesForCircle(circleId);
    final match = contractFiles.firstWhere(
      (f) =>
          (f['id'] ?? '').toString() == fileId ||
          (f['_id'] ?? '').toString() == fileId,
      orElse: () => <String, dynamic>{},
    );
    if (match.isEmpty) {
      return Future.error(Exception('File $fileId not found'));
    }
    return CircleFileDto.fromMap({
      ...Map<String, dynamic>.from(match),
      'circleId': circleId,
    });
  }

  @override
  Future<CircleFileDto> updateFile(
    String circleId,
    String fileId,
    CircleFileUpdateWireDto data,
  ) async {
    final existing = await getFile(circleId, fileId);
    return CircleFileDto.fromMap({
      ...existing.toMap(),
      ...data.toMap(),
      'circleId': circleId,
    });
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {}

  @override
  Future<void> updateSections(
    String circleId,
    List<CircleSectionConfigDto> sections,
  ) async {}

  @override
  Future<void> reportBehavior(CircleBehaviorReportWireDto report) async {}

  @override
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _copyCircleDtos().take(limit).toList(growable: false);
  }

  @override
  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    final contractRows = CircleContractSeedHelpers.homeFeedRows();
    if (contractRows.isNotEmpty) {
      return _decodeCircleFeedMaps(
        contractRows.take(limit).map((e) => Map<String, dynamic>.from(e)),
      );
    }
    return const <PostBaseDto>[];
  }

  @override
  List<CircleDto> publishFlowRecommendedCircles() {
    final now = DateTime.now().toUtc();
    return <CircleDto>[
      CircleDto(
        id: 'rec-city',
        name: '城市探索',
        coverUrl:
            'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=400',
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
            'https://images.unsplash.com/photo-1486218119243-13883505764c?q=80&w=400',
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
    return CircleCategoryTabsLoader.loadFromAsset();
  }
}
