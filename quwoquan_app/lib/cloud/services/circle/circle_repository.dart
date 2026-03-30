import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

/// 首页圈子发现流单次拉取上限（产品约定，非 [CloudApiDefaults.pageLimit]）。
const int _kHomeCircleDiscoveryFeedDefaultLimit = 200;

String? _normalizeCircleFeedType(String? type) {
  final normalized = (type ?? '').trim().toLowerCase();
  switch (normalized) {
    case '':
      return null;
    case 'photo':
      return 'image';
    case 'note':
      return 'article';
    default:
      return normalized;
  }
}

/// Circle 域 Repository（三层模式：Abstract + Mock + Remote）。
///
/// Mock：使用 [CircleMockData]（canonical 字段数据），不发 HTTP。
/// Remote：对接云侧 REST 契约，使用 [CloudRuntimeConfig] + [CloudRequestHeaders]。
abstract class CircleRepository {
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  });

  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<Map<String, dynamic>> getCircle(String circleId);

  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data);

  Future<Map<String, dynamic>> updateCircle(
    String circleId,
    Map<String, dynamic> data,
  );

  Future<void> archiveCircle(String circleId);

  Future<void> joinCircle(String circleId);

  Future<void> leaveCircle(String circleId);

  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<void> updateMemberRole(String circleId, String userId, String role);

  Future<List<Map<String, dynamic>>> listCircleGroups(
    String circleId, {
    String? groupType,
    String? visibility,
    String? parentGroupId,
    String? nodeType,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<Map<String, dynamic>>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<Map<String, dynamic>> getCircleGroup(String circleId, String groupId);

  Future<Map<String, dynamic>> createCircleGroup(
    String circleId,
    Map<String, dynamic> data,
  );

  Future<Map<String, dynamic>> updateCircleGroup(
    String circleId,
    String groupId,
    Map<String, dynamic> data,
  );

  Future<void> applyJoinCircleGroup(String circleId, String groupId);

  Future<List<Map<String, dynamic>>> listCircleGroupMembers(
    String circleId,
    String groupId, {
    String? status,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  );

  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  );

  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  });

  Future<void> pinPost(String circleId, String postId, {required bool pinned});

  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  });

  Future<Map<String, dynamic>> getCircleStats(String circleId);

  Future<List<Map<String, dynamic>>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  );

  Future<Map<String, dynamic>> getFile(String circleId, String fileId);

  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  );

  Future<void> deleteFile(String circleId, String fileId);

  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  );

  Future<void> reportBehavior(Map<String, dynamic> report);

  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 首页圈子发现流（Mock：`CircleMockData.circleFeedItems`；Remote：空列表）。
  Future<List<Map<String, dynamic>>> listHomeCircleDiscoveryFeed({
    int limit = _kHomeCircleDiscoveryFeedDefaultLimit,
  });

  /// 圈子分类 Tab 配置（Mock：`categoryConfig`；Remote：仅 `all`）。
  Future<Map<String, Map<String, dynamic>>> getCircleCategoryConfig();
}

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

class MockCircleRepository implements CircleRepository {
  MockCircleRepository() : _circles = _buildInitialCircles();

  final List<Map<String, dynamic>> _circles;
  final Map<String, List<Map<String, dynamic>>> _groupCache = {};
  final Map<String, List<Map<String, dynamic>>> _groupMembersCache = {};

  static List<Map<String, dynamic>> _buildInitialCircles() {
    final source = <Map<String, dynamic>>[
      CircleMockData.circleInfo,
      ...CircleMockData.circles,
    ];
    final circlesById = <String, Map<String, dynamic>>{};
    for (final circle in source) {
      final id = (circle['id'] ?? circle['_id'] ?? '').toString();
      if (id.isEmpty) {
        continue;
      }
      circlesById[id] = Map<String, dynamic>.from(circle);
    }
    return circlesById.values.toList(growable: true);
  }

  List<Map<String, dynamic>> _copyCircles() {
    return _circles
        .map((circle) => Map<String, dynamic>.from(circle))
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _ensureGroupCache(String circleId) {
    final existing = _groupCache[circleId];
    if (existing != null) {
      return existing;
    }
    final circle = _circles.firstWhere(
      (item) => item['id'] == circleId || item['_id'] == circleId,
      orElse: () => <String, dynamic>{},
    );
    final now = DateTime.now().toIso8601String();
    final circleName = (circle['name'] ?? '群组').toString().trim();
    final description = (circle['description'] ?? '').toString().trim();
    final ownerUserId = (circle['ownerId'] ?? 'owner_user').toString().trim();
    final groups = <Map<String, dynamic>>[
      _normalizedCircleGroup(
        <String, dynamic>{
          'name': '$circleName主群',
          'description': description.isEmpty ? '默认公共群' : '$description · 默认公共群',
          'groupType': 'public_group',
          'visibility': 'public',
          'joinPolicy': 'apply_only',
          'ownerUserId': ownerUserId,
          'memberCount': (circle['memberCount'] as num?)?.toInt() ?? 0,
          'conversationId': circle['conversationId']?.toString(),
          'isDefaultPublicGroup': true,
          'lastActiveAt': circle['updatedAt'] ?? now,
        },
        circleId: circleId,
        groupId: '${circleId}_group_default',
        fallbackUpdatedAt: now,
      ),
    ];
    final displaySubjectType = (circle['displaySubjectType'] ?? 'circle')
        .toString()
        .trim();
    if (displaySubjectType != 'circle') {
      groups.add(
        _normalizedCircleGroup(
          <String, dynamic>{
            'name': circleName,
            'description': description,
            'groupType': 'org_node',
            'nodeType': 'generic',
            'visibility': 'public',
            'joinPolicy': 'apply_only',
            'ownerUserId': ownerUserId,
            'memberCount': (circle['memberCount'] as num?)?.toInt() ?? 0,
            'lastActiveAt': circle['updatedAt'] ?? now,
          },
          circleId: circleId,
          groupId: '${circleId}_node_root',
          fallbackUpdatedAt: now,
        ),
      );
    }
    _groupCache[circleId] = groups;
    return groups;
  }

  List<Map<String, dynamic>> _ensureGroupMembersCache(
    String circleId,
    String groupId,
  ) {
    final key = '$circleId::$groupId';
    final existing = _groupMembersCache[key];
    if (existing != null) {
      return existing;
    }
    final group = _ensureGroupCache(circleId).firstWhere(
      (item) => item['id'] == groupId || item['_id'] == groupId,
      orElse: () => <String, dynamic>{},
    );
    final ownerUserId = (group['ownerUserId'] ?? 'owner_user')
        .toString()
        .trim();
    final now = DateTime.now().toIso8601String();
    final members = <Map<String, dynamic>>[
      <String, dynamic>{
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
      },
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
      'tags': (data['tags'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => item.toString())
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
      'managerIds': (data['managerIds'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => item.toString())
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
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  }) async {
    var result = _copyCircles();
    if (category != null) {
      result = result
          .where((c) => c['categoryId'] == category)
          .toList(growable: false);
    }
    if (subCategory != null) {
      result = result
          .where((c) => c['subCategory'] == subCategory)
          .toList(growable: false);
    }
    if (domainId != null) {
      result = result
          .where((c) => c['domainId'] == domainId)
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
    final filtered = _copyCircles()
        .where((circle) {
          if (categoryId != null &&
              categoryId.isNotEmpty &&
              circle['categoryId']?.toString() != categoryId) {
            return false;
          }
          if (subCategory != null &&
              subCategory.isNotEmpty &&
              circle['subCategory']?.toString() != subCategory) {
            return false;
          }
          final name = (circle['name'] ?? '').toString().toLowerCase();
          final description = (circle['description'] ?? '')
              .toString()
              .toLowerCase();
          return name.contains(normalizedQuery) ||
              description.contains(normalizedQuery);
        })
        .toList(growable: false);
    final items = filtered
        .take(limit)
        .map((circle) {
          final name = (circle['name'] ?? '').toString();
          return CircleSearchItemView.fromMap(<String, dynamic>{
            ...circle,
            'circleId': circle['circleId'] ?? circle['id'],
            'highlightText': name,
            'matchedField': 'name',
          });
        })
        .toList(growable: false);
    final facetCounts = <String, int>{};
    for (final circle in filtered) {
      final key = (circle['subCategory'] ?? circle['categoryId'] ?? '')
          .toString()
          .trim();
      if (key.isEmpty) {
        continue;
      }
      facetCounts.update(key, (value) => value + 1, ifAbsent: () => 1);
    }
    final facetBuckets = filtered
        .map(
          (circle) => <String, dynamic>{
            'facetKey': (circle['subCategory'] ?? circle['categoryId'] ?? '')
                .toString(),
            'label': (circle['subCategory'] ?? circle['categoryId'] ?? '')
                .toString(),
            'categoryId': circle['categoryId']?.toString(),
            'subCategory': circle['subCategory']?.toString(),
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
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    final match = _circles.firstWhere(
      (c) => c['id'] == circleId,
      orElse: () => <String, dynamic>{},
    );
    if (match.isEmpty) {
      return Future.error(Exception('Circle $circleId not found'));
    }
    return Map<String, dynamic>.from(match);
  }

  @override
  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data) async {
    final circleId = (data['id']?.toString().trim().isNotEmpty ?? false)
        ? data['id'].toString().trim()
        : 'local_${DateTime.now().millisecondsSinceEpoch}';
    final created = _normalizedCircle(data, circleId: circleId);
    _circles.removeWhere((circle) => circle['id'] == circleId);
    _circles.insert(0, created);
    return Map<String, dynamic>.from(created);
  }

  @override
  Future<Map<String, dynamic>> updateCircle(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final existing = await getCircle(circleId);
    final updatedAt = DateTime.now().toIso8601String();
    final merged = _normalizedCircle(
      <String, dynamic>{...existing, ...data, 'updatedAt': updatedAt},
      circleId: circleId,
      fallbackUpdatedAt: updatedAt,
    );
    final index = _circles.indexWhere((circle) => circle['id'] == circleId);
    if (index >= 0) {
      _circles[index] = merged;
    } else {
      _circles.insert(0, merged);
    }
    return Map<String, dynamic>.from(merged);
  }

  @override
  Future<void> archiveCircle(String circleId) async {}

  @override
  Future<void> joinCircle(String circleId) async {}

  @override
  Future<void> leaveCircle(String circleId) async {}

  @override
  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return CircleMockData.members.take(limit).toList(growable: false);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {}

  @override
  Future<List<Map<String, dynamic>>> listCircleGroups(
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
          .where((group) => group['groupType']?.toString() == groupType)
          .toList(growable: false);
    }
    if (visibility != null && visibility.isNotEmpty) {
      groups = groups
          .where((group) => group['visibility']?.toString() == visibility)
          .toList(growable: false);
    }
    if (parentGroupId != null && parentGroupId.isNotEmpty) {
      groups = groups
          .where((group) => group['parentGroupId']?.toString() == parentGroupId)
          .toList(growable: false);
    }
    if (nodeType != null && nodeType.isNotEmpty) {
      groups = groups
          .where((group) => group['nodeType']?.toString() == nodeType)
          .toList(growable: false);
    }
    return groups
        .take(limit)
        .map((group) => Map<String, dynamic>.from(group))
        .toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <Map<String, dynamic>>[];
    }
    final groups = await listCircleGroups(
      circleId,
      groupType: groupType,
      visibility: visibility,
      limit: 100,
    );
    return groups
        .where((group) {
          final name = (group['name'] ?? '').toString().toLowerCase();
          final description = (group['description'] ?? '')
              .toString()
              .toLowerCase();
          return name.contains(normalizedQuery) ||
              description.contains(normalizedQuery);
        })
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<Map<String, dynamic>> getCircleGroup(
    String circleId,
    String groupId,
  ) async {
    final group = _ensureGroupCache(circleId).firstWhere(
      (item) => item['id'] == groupId || item['_id'] == groupId,
      orElse: () => <String, dynamic>{},
    );
    if (group.isEmpty) {
      return Future.error(Exception('Circle group $groupId not found'));
    }
    return Map<String, dynamic>.from(group);
  }

  @override
  Future<Map<String, dynamic>> createCircleGroup(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final now = DateTime.now().toIso8601String();
    final groupId = (data['id']?.toString().trim().isNotEmpty ?? false)
        ? data['id'].toString().trim()
        : 'local_group_${DateTime.now().millisecondsSinceEpoch}';
    final group = _normalizedCircleGroup(
      <String, dynamic>{...data, 'createdAt': now, 'updatedAt': now},
      circleId: circleId,
      groupId: groupId,
      fallbackUpdatedAt: now,
    );
    final groups = _ensureGroupCache(circleId);
    groups.removeWhere(
      (item) => item['id'] == groupId || item['_id'] == groupId,
    );
    groups.insert(0, group);
    _groupMembersCache['$circleId::$groupId'] = <Map<String, dynamic>>[
      <String, dynamic>{
        '_id': '${groupId}_${group['ownerUserId']}',
        'id': '${groupId}_${group['ownerUserId']}',
        'groupId': groupId,
        'circleId': circleId,
        'userId': group['ownerUserId'],
        'role': 'owner',
        'status': 'joined',
        'joinedAt': now,
        'createdAt': now,
        'updatedAt': now,
      },
    ];
    return Map<String, dynamic>.from(group);
  }

  @override
  Future<Map<String, dynamic>> updateCircleGroup(
    String circleId,
    String groupId,
    Map<String, dynamic> data,
  ) async {
    final existing = await getCircleGroup(circleId, groupId);
    final now = DateTime.now().toIso8601String();
    final merged = _normalizedCircleGroup(
      <String, dynamic>{...existing, ...data, 'updatedAt': now},
      circleId: circleId,
      groupId: groupId,
      fallbackUpdatedAt: now,
    );
    final groups = _ensureGroupCache(circleId);
    final index = groups.indexWhere(
      (item) => item['id'] == groupId || item['_id'] == groupId,
    );
    if (index >= 0) {
      groups[index] = merged;
    } else {
      groups.insert(0, merged);
    }
    return Map<String, dynamic>.from(merged);
  }

  @override
  Future<void> applyJoinCircleGroup(String circleId, String groupId) async {
    const currentUserId = 'current_user';
    final members = _ensureGroupMembersCache(circleId, groupId);
    final now = DateTime.now().toIso8601String();
    final index = members.indexWhere(
      (item) => item['userId']?.toString() == currentUserId,
    );
    final pendingMember = <String, dynamic>{
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
      members[index] = <String, dynamic>{...members[index], ...pendingMember};
    } else {
      members.add(pendingMember);
    }
  }

  @override
  Future<List<Map<String, dynamic>>> listCircleGroupMembers(
    String circleId,
    String groupId, {
    String? status,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var members = _ensureGroupMembersCache(circleId, groupId);
    if (status != null && status.isNotEmpty) {
      members = members
          .where((member) => member['status']?.toString() == status)
          .toList(growable: false);
    }
    return members
        .take(limit)
        .map((member) => Map<String, dynamic>.from(member))
        .toList(growable: false);
  }

  @override
  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final members = _ensureGroupMembersCache(circleId, groupId);
    final index = members.indexWhere(
      (member) => member['userId']?.toString() == userId,
    );
    if (index < 0) {
      return;
    }
    final now = DateTime.now().toIso8601String();
    final wasJoined = members[index]['status']?.toString() == 'joined';
    members[index] = <String, dynamic>{
      ...members[index],
      'status': 'joined',
      'joinedAt': members[index]['joinedAt'] ?? now,
      'decidedAt': now,
      'updatedAt': now,
    };
    if (wasJoined) {
      return;
    }
    final groups = _ensureGroupCache(circleId);
    final groupIndex = groups.indexWhere(
      (group) => group['id'] == groupId || group['_id'] == groupId,
    );
    if (groupIndex >= 0) {
      groups[groupIndex] = <String, dynamic>{
        ...groups[groupIndex],
        'memberCount':
            ((groups[groupIndex]['memberCount'] as num?)?.toInt() ?? 0) + 1,
        'lastActiveAt': now,
        'updatedAt': now,
      };
    }
  }

  @override
  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final members = _ensureGroupMembersCache(circleId, groupId);
    final index = members.indexWhere(
      (member) => member['userId']?.toString() == userId,
    );
    if (index < 0) {
      return;
    }
    final now = DateTime.now().toIso8601String();
    members[index] = <String, dynamic>{
      ...members[index],
      'status': 'rejected',
      'decidedAt': now,
      'updatedAt': now,
    };
  }

  @override
  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  }) async {
    final normalizedType = _normalizeCircleFeedType(type);
    return CircleMockData.circleFeedItems
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
  Future<Map<String, dynamic>> getCircleStats(String circleId) async {
    return CircleMockData.stats;
  }

  @override
  Future<List<Map<String, dynamic>>> listFiles(
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
    return result.take(limit).toList(growable: false);
  }

  @override
  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    return <String, dynamic>{
      ...data,
      'id': 'f_${DateTime.now().millisecondsSinceEpoch}',
      'createdAt': DateTime.now().toIso8601String(),
    };
  }

  @override
  Future<Map<String, dynamic>> getFile(String circleId, String fileId) async {
    final match = CircleMockData.files.firstWhere(
      (f) => f['id'] == fileId,
      orElse: () => <String, dynamic>{},
    );
    if (match.isEmpty) {
      return Future.error(Exception('File $fileId not found'));
    }
    return match;
  }

  @override
  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  ) async {
    final existing = await getFile(circleId, fileId);
    return <String, dynamic>{...existing, ...data};
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {}

  @override
  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  ) async {}

  @override
  Future<void> reportBehavior(Map<String, dynamic> report) async {}

  @override
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _copyCircles().take(limit).toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> listHomeCircleDiscoveryFeed({
    int limit = _kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    return CircleMockData.circleFeedItems
        .take(limit)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(growable: false);
  }

  @override
  Future<Map<String, Map<String, dynamic>>> getCircleCategoryConfig() async {
    return Map<String, Map<String, dynamic>>.fromEntries(
      CircleMockData.categoryConfig.entries.map(
        (e) => MapEntry(e.key, Map<String, dynamic>.from(e.value)),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Remote
// ---------------------------------------------------------------------------

class RemoteCircleRepository implements CircleRepository {
  RemoteCircleRepository({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  // -- Circles ---------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (category != null) query['category'] = category;
    if (subCategory != null) query['subCategory'] = subCategory;
    if (domainId != null) query['domainId'] = domainId;
    if (recommendFor != null) query['recommendFor'] = recommendFor;
    if (cursor != null) query['cursor'] = cursor;
    if (sort != null) query['sort'] = sort;

    final uri = _uri(CircleApiMetadata.listCirclesPath, queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.listCircles),
    );
    return _decodeList(resp);
  }

  @override
  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final resp = await _client.get(
      _uri(
        CircleApiMetadata.searchCirclesPath,
        queryParameters: <String, String>{
          'query': query,
          if (categoryId != null && categoryId.isNotEmpty)
            'categoryId': categoryId,
          if (subCategory != null && subCategory.isNotEmpty)
            'subCategory': subCategory,
          'limit': '$limit',
        },
      ),
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.searchCircles),
    );
    return CircleSearchResultView.fromMap(_decodeObject(resp));
  }

  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.getCirclePath(circleId: circleId));
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircle),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data) async {
    final uri = _uri(CircleApiMetadata.createCirclePath);
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircle),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> updateCircle(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(CircleApiMetadata.updateCirclePath(circleId: circleId));
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircle),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> archiveCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.archiveCirclePath(circleId: circleId));
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.archiveCircle),
    );
    _ensureSuccess(resp);
  }

  // -- Membership ------------------------------------------------------------

  @override
  Future<void> joinCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.joinCirclePath(circleId: circleId));
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.joinCircle),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> leaveCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.leaveCirclePath(circleId: circleId));
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.leaveCircle),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listCircleMembersPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleMembers,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateMemberRolePath(
        circleId: circleId,
        userId: userId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateMemberRole),
        'Content-Type': 'application/json',
      },
      body: json.encode({'role': role}),
    );
    _ensureSuccess(resp);
  }

  // -- Circle Groups ----------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listCircleGroups(
    String circleId, {
    String? groupType,
    String? visibility,
    String? parentGroupId,
    String? nodeType,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (groupType != null && groupType.isNotEmpty) {
      query['groupType'] = groupType;
    }
    if (visibility != null && visibility.isNotEmpty) {
      query['visibility'] = visibility;
    }
    if (parentGroupId != null && parentGroupId.isNotEmpty) {
      query['parentGroupId'] = parentGroupId;
    }
    if (nodeType != null && nodeType.isNotEmpty) query['nodeType'] = nodeType;
    if (cursor != null && cursor.isNotEmpty) query['cursor'] = cursor;
    final uri = _uri(
      CircleApiMetadata.listCircleGroupsPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleGroups,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<List<Map<String, dynamic>>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      CircleApiMetadata.searchCircleGroupsPath(circleId: circleId),
      queryParameters: <String, String>{
        'query': query,
        if (visibility != null && visibility.isNotEmpty)
          'visibility': visibility,
        if (groupType != null && groupType.isNotEmpty) 'groupType': groupType,
        'limit': '$limit',
      },
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.searchCircleGroups,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<Map<String, dynamic>> getCircleGroup(
    String circleId,
    String groupId,
  ) async {
    final uri = _uri(
      CircleApiMetadata.getCircleGroupPath(
        circleId: circleId,
        groupId: groupId,
      ),
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleGroup),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> createCircleGroup(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.createCircleGroupPath(circleId: circleId),
    );
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleGroup),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> updateCircleGroup(
    String circleId,
    String groupId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleGroupPath(
        circleId: circleId,
        groupId: groupId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleGroup),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> applyJoinCircleGroup(String circleId, String groupId) async {
    final uri = _uri(
      CircleApiMetadata.applyJoinCircleGroupPath(
        circleId: circleId,
        groupId: groupId,
      ),
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.applyJoinCircleGroup,
      ),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<List<Map<String, dynamic>>> listCircleGroupMembers(
    String circleId,
    String groupId, {
    String? status,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (status != null && status.isNotEmpty) query['status'] = status;
    if (cursor != null && cursor.isNotEmpty) query['cursor'] = cursor;
    final uri = _uri(
      CircleApiMetadata.listCircleGroupMembersPath(
        circleId: circleId,
        groupId: groupId,
      ),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleGroupMembers,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final uri = _uri(
      CircleApiMetadata.approveCircleGroupMemberPath(
        circleId: circleId,
        groupId: groupId,
        userId: userId,
      ),
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.approveCircleGroupMember,
      ),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final uri = _uri(
      CircleApiMetadata.rejectCircleGroupMemberPath(
        circleId: circleId,
        groupId: groupId,
        userId: userId,
      ),
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.rejectCircleGroupMember,
      ),
    );
    _ensureSuccess(resp);
  }

  // -- Feed ------------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  }) async {
    final query = <String, String>{'limit': '$limit', 'sort': sort};
    if (cursor != null) query['cursor'] = cursor;
    if (identity != null && identity.isNotEmpty) query['identity'] = identity;
    final normalizedType = _normalizeCircleFeedType(type);
    if (normalizedType != null && normalizedType.isNotEmpty) {
      query['type'] = normalizedType;
    }

    final uri = _uri(
      CircleApiMetadata.getCircleFeedPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFeed),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {
    final uri = _uri(
      CircleApiMetadata.pinCirclePostPath(circleId: circleId, postId: postId),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.pinCirclePost),
        'Content-Type': 'application/json',
      },
      body: json.encode({'pinned': pinned}),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  }) async {
    final uri = _uri(
      CircleApiMetadata.featureCirclePostPath(
        circleId: circleId,
        postId: postId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.featureCirclePost),
        'Content-Type': 'application/json',
      },
      body: json.encode({'featured': featured}),
    );
    _ensureSuccess(resp);
  }

  // -- Stats -----------------------------------------------------------------

  @override
  Future<Map<String, dynamic>> getCircleStats(String circleId) async {
    final uri = _uri(CircleApiMetadata.getCircleStatsPath(circleId: circleId));
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleStats),
    );
    return _decodeObject(resp);
  }

  // -- Files -----------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (parentId != null) query['parentId'] = parentId;
    if (sort != null) query['sort'] = sort;
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listCircleFilesPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleFiles,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.createCircleFilePath(circleId: circleId),
    );
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleFile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> getFile(String circleId, String fileId) async {
    final uri = _uri(
      CircleApiMetadata.getCircleFilePath(circleId: circleId, fileId: fileId),
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFile),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleFilePath(
        circleId: circleId,
        fileId: fileId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleFile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {
    final uri = _uri(
      CircleApiMetadata.deleteCircleFilePath(
        circleId: circleId,
        fileId: fileId,
      ),
    );
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.deleteCircleFile,
      ),
    );
    _ensureSuccess(resp);
  }

  // -- Sections --------------------------------------------------------------

  @override
  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleSectionsPath(circleId: circleId),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(
          CircleRequestPageIds.updateCircleSections,
        ),
        'Content-Type': 'application/json',
      },
      body: json.encode({'sections': sections}),
    );
    _ensureSuccess(resp);
  }

  // -- Behavior --------------------------------------------------------------

  @override
  Future<void> reportBehavior(Map<String, dynamic> report) async {
    final uri = _uri(CircleApiMetadata.reportCircleBehaviorPath);
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(
          CircleRequestPageIds.reportCircleBehavior,
        ),
        'Content-Type': 'application/json',
      },
      body: json.encode(report),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<List<Map<String, dynamic>>> listHomeCircleDiscoveryFeed({
    int limit = _kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    return const [];
  }

  @override
  Future<Map<String, Map<String, dynamic>>> getCircleCategoryConfig() async {
    return const {
      'all': {'label': '推荐'},
    };
  }

  // -- User Circles ----------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listUserCirclesPath(userId: userId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listUserCircles,
      ),
    );
    return _decodeList(resp);
  }

  // -- Helpers ---------------------------------------------------------------

  void _ensureSuccess(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('Circle API error ${resp.statusCode}: ${resp.body}');
    }
  }

  Map<String, dynamic> _decodeObject(http.Response resp) {
    _ensureSuccess(resp);
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) {
      return (decoded['data'] as Map<String, dynamic>?) ?? decoded;
    }
    throw FormatException('Expected JSON object, got ${decoded.runtimeType}');
  }

  List<Map<String, dynamic>> _decodeList(http.Response resp) {
    _ensureSuccess(resp);
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) {
      final items = decoded['data'] ?? decoded['items'] ?? [];
      return (items as List).cast<Map<String, dynamic>>();
    }
    if (decoded is List) {
      return decoded.cast<Map<String, dynamic>>();
    }
    throw FormatException('Expected JSON list, got ${decoded.runtimeType}');
  }
}
