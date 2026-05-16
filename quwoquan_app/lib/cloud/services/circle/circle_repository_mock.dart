part of 'circle_repository.dart';

/// Mock 详情 wire：在 [CircleDto.toMap] 上补齐 UI/Mock 仍消费的别名键与主圈视角字段。
Map<String, dynamic> _mockCircleDetailWireFromDto(CircleDto d) {
  final w = Map<String, dynamic>.from(d.toMap());
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
  if (d.id == CircleMockData.primaryCircleId) {
    final p = CircleMockData.circleInfo;
    w['stats'] = p['stats'];
    w['hasNewMessages'] = p['hasNewMessages'];
    w['role'] = p['role'];
    w['joinStatus'] = p['joinStatus'];
    w['isFollowed'] = p['isFollowed'];
  } else {
    w.putIfAbsent('role', () => 'member');
    w.putIfAbsent('joinStatus', () => 'none');
    w.putIfAbsent('isFollowed', () => false);
  }
  return w;
}

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

class MockCircleRepository implements CircleRepository {
  MockCircleRepository({List<CircleDto>? seedCircles})
    : _circles = seedCircles ?? _repositorySeedCircles();

  final List<CircleDto> _circles;
  final Map<String, List<CircleGroupDto>> _groupCache = {};
  final Map<String, List<CircleGroupMemberDto>> _groupMembersCache = {};

  static List<CircleDto>? _contractSeedCircles() {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet();
    final circles = seed?['circles'];
    if (circles is! List) {
      return null;
    }
    return circles
        .whereType<Map>()
        .map((item) => CircleDto.fromMap(item.cast<String, dynamic>()))
        .toList(growable: true);
  }

  static List<CircleDto> _repositorySeedCircles() {
    final byId = <String, CircleDto>{};
    void put(CircleDto circle) {
      byId[circle.id] = circle;
    }

    for (final circle in _contractSeedCircles() ?? const <CircleDto>[]) {
      put(circle);
    }
    for (final circle in CircleMockData.buildRepositorySeedCircleDtos()) {
      put(circle);
    }
    return byId.values.toList(growable: true);
  }

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
    final circle = _findCircle(circleId);
    if (circle == null) {
      _groupCache[circleId] = <CircleGroupDto>[];
      return _groupCache[circleId]!;
    }
    final now = DateTime.now().toIso8601String();
    final circleName = circle.name.trim().isEmpty ? '群组' : circle.name.trim();
    final description = (circle.description ?? '').trim();
    final ownerUserId = circle.ownerId.trim().isEmpty
        ? 'owner_user'
        : circle.ownerId.trim();
    final groups = <CircleGroupDto>[
      CircleGroupDto.fromMap(
        _normalizedCircleGroup(
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
            'conversationId': circle.conversationId,
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
          _normalizedCircleGroup(
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

  Map<String, dynamic> _normalizedCircle(
    Map<String, dynamic> data, {
    required String circleId,
    String? fallbackUpdatedAt,
  }) {
    final now = DateTime.now().toIso8601String();
    final coverUrl = (data['coverUrl'] ?? data['cover'] ?? '')
        .toString()
        .trim();
    final avatarUrl = (data['avatarUrl'] ?? data['avatar'] ?? coverUrl)
        .toString()
        .trim();
    final description = (data['description'] ?? data['desc'] ?? '')
        .toString()
        .trim();
    return <String, dynamic>{
      ...data,
      'id': circleId,
      'description': description,
      'desc': description,
      'coverUrl': coverUrl,
      'cover': (data['cover'] ?? coverUrl).toString(),
      'avatar': avatarUrl,
      'avatarUrl': avatarUrl,
      'memberCount': (data['memberCount'] as num?)?.toInt() ?? 1,
      'postCount': (data['postCount'] as num?)?.toInt() ?? 0,
      'weeklyActiveCount': (data['weeklyActiveCount'] as num?)?.toInt() ?? 0,
      'status': (data['status'] ?? 'active').toString(),
      'visibility': (data['visibility'] ?? 'public').toString(),
      'joinPolicy': (data['joinPolicy'] ?? 'open').toString(),
      'kind': (data['kind'] ?? 'interest').toString(),
      'displaySubjectType': (data['displaySubjectType'] ?? 'circle').toString(),
      'followEnabled': data['followEnabled'] as bool? ?? true,
      'defaultPublicGroupId':
          (data['defaultPublicGroupId'] ?? '${circleId}_group_default')
              .toString(),
      'autoSyncChat': data['autoSyncChat'] as bool? ?? true,
      'tags': ((data['tags'] as List?) ?? const <Object?>[])
          .map((Object? item) => item.toString())
          .toList(growable: false),
      'createdAt': data['createdAt'] ?? fallbackUpdatedAt ?? now,
      'updatedAt': data['updatedAt'] ?? fallbackUpdatedAt ?? now,
      'role': (data['role'] ?? 'owner').toString(),
      'joinStatus': (data['joinStatus'] ?? 'joined').toString(),
      'isFollowed': data['isFollowed'] as bool? ?? true,
    };
  }

  Map<String, dynamic> _normalizedCircleGroup(
    Map<String, dynamic> data, {
    required String circleId,
    required String groupId,
    String? fallbackUpdatedAt,
  }) {
    final now = fallbackUpdatedAt ?? DateTime.now().toIso8601String();
    return <String, dynamic>{
      ...data,
      '_id': groupId,
      'id': groupId,
      'circleId': circleId,
      if (data['parentGroupId'] != null)
        'parentGroupId': data['parentGroupId'].toString(),
      'groupType': (data['groupType'] ?? 'public_group').toString(),
      if (data['nodeType'] != null) 'nodeType': data['nodeType'].toString(),
      'name': (data['name'] ?? '未命名群组').toString(),
      'description': (data['description'] ?? '').toString(),
      'visibility': (data['visibility'] ?? 'public').toString(),
      'joinPolicy': (data['joinPolicy'] ?? 'apply_only').toString(),
      'ownerUserId': (data['ownerUserId'] ?? 'owner_user').toString(),
      'managerIds': ((data['managerIds'] as List?) ?? const <Object?>[])
          .map((Object? item) => item.toString())
          .toList(growable: false),
      'memberCount': (data['memberCount'] as num?)?.toInt() ?? 0,
      if (data['conversationId'] != null)
        'conversationId': data['conversationId'].toString(),
      'storageEnabled': data['storageEnabled'] as bool? ?? true,
      'noticeEnabled': data['noticeEnabled'] as bool? ?? true,
      'isDefaultPublicGroup': data['isDefaultPublicGroup'] as bool? ?? false,
      'lastActiveAt': data['lastActiveAt'] ?? now,
      'status': (data['status'] ?? 'active').toString(),
      'createdAt': data['createdAt'] ?? now,
      'updatedAt': data['updatedAt'] ?? now,
    };
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
    final created = _normalizedCircle(merge, circleId: circleId);
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
    final merged = _normalizedCircle(
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
    return CircleMockData.members
        .take(limit)
        .map(
          (m) => CircleMemberRosterItemDto.fromMap(
            Map<String, dynamic>.from(m),
            circleId: circleId,
          ),
        )
        .toList(growable: false);
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
    final groupWire = _normalizedCircleGroup(
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
    final mergedWire = _normalizedCircleGroup(
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
        _normalizedCircleGroup(
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
    final maps = CircleMockData.circleFeedItems
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
    return CircleMockData.catalogCircleStatsWire;
  }

  @override
  Future<List<CircleFileDto>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var result = CircleMockData.files;
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
    final match = CircleMockData.files.firstWhere(
      (f) => f['id'] == fileId,
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
    return _decodeCircleFeedMaps(
      CircleMockData.circleFeedItems
          .take(limit)
          .map((e) => Map<String, dynamic>.from(e)),
    );
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
