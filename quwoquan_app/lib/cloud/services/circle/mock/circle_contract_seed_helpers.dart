import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';

class CircleContractSeedHelpers {
  const CircleContractSeedHelpers._();

  static List<CircleDto>? seedCircles() {
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

  static List<Map<String, dynamic>> mapRows(Object? raw) {
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    return raw
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  }

  static List<String> stringList(Object? raw) {
    if (raw is! List) {
      return const <String>[];
    }
    return raw
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }

  static int intValue(dynamic value, {int fallback = 0}) {
    if (value is num) {
      return value.toInt();
    }
    if (value is String) {
      return int.tryParse(value.trim()) ?? fallback;
    }
    return fallback;
  }

  static List<Map<String, dynamic>> circleRows() {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet();
    return mapRows(seed?['circles']);
  }

  static Map<String, dynamic>? circleRowById(String circleId) {
    for (final row in circleRows()) {
      if ((row['id'] ?? '').toString().trim() == circleId) {
        return row;
      }
    }
    return null;
  }

  static List<Map<String, dynamic>> groupsForCircle(String circleId) {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet();
    final groups = seed?['groups'];
    if (groups is! Map) {
      return const <Map<String, dynamic>>[];
    }
    return mapRows(groups[circleId]);
  }

  static List<Map<String, dynamic>> membersForCircle(String circleId) {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet();
    final members = seed?['members'];
    if (members is! Map) {
      return const <Map<String, dynamic>>[];
    }
    return mapRows(members[circleId]);
  }

  static List<Map<String, dynamic>> filesForCircle(String circleId) {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet();
    final files = seed?['files'];
    if (files is! Map) {
      return const <Map<String, dynamic>>[];
    }
    return mapRows(files[circleId]);
  }

  static Map<String, dynamic>? statsForCircle(String circleId) {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet(
      'circle_profile_core',
    );
    final stats = mapRows(seed?['stats']);
    for (final row in stats) {
      if ((row['circleId'] ?? '').toString().trim() == circleId) {
        return row;
      }
    }
    return null;
  }

  static List<Map<String, dynamic>> contentPostRows() {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet();
    return mapRows(seed?['posts']);
  }

  static List<Map<String, dynamic>> contentPostRowsByIds(
    Iterable<String> postIds,
  ) {
    final wanted = postIds
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toSet();
    if (wanted.isEmpty) {
      return const <Map<String, dynamic>>[];
    }
    final selected = <Map<String, dynamic>>[];
    for (final row in contentPostRows()) {
      final postId = (row['postId'] ?? row['id'] ?? '').toString().trim();
      if (wanted.contains(postId)) {
        selected.add(Map<String, dynamic>.from(row));
      }
    }
    return selected;
  }

  static List<Map<String, dynamic>> circleFeedRows(String circleId) {
    final profileSeed = ContractFixtureRuntimeLoader.circleSeedSet(
      'circle_profile_core',
    );
    final profileCircleIds = stringList(profileSeed?['circleIds']);
    if (profileCircleIds.contains(circleId)) {
      final rows = contentPostRowsByIds(stringList(profileSeed?['postIds']));
      if (rows.isNotEmpty) {
        return rows;
      }
    }
    return contentPostRows()
        .where((row) => _postBelongsToCircle(row, circleId))
        .map((row) => Map<String, dynamic>.from(row))
        .toList(growable: false);
  }

  static List<Map<String, dynamic>> homeFeedRows() {
    final homeSeed = ContractFixtureRuntimeLoader.circleSeedSet(
      'circle_home_feed_core',
    );
    return contentPostRowsByIds(stringList(homeSeed?['groupFeedPostIds']));
  }

  static List<CircleDto> repositorySeedCircles() {
    final byId = <String, CircleDto>{};
    void put(CircleDto circle) {
      byId[circle.id] = circle;
    }

    for (final circle in CircleMockData.buildRepositorySeedCircleDtos()) {
      put(circle);
    }
    for (final circle in seedCircles() ?? const <CircleDto>[]) {
      put(circle);
    }
    return byId.values.toList(growable: true);
  }

  static Map<String, dynamic> normalizedCircle(
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
    final rawTags =
        (data['tags'] as List?)?.cast<Object?>() ?? const <Object?>[];
    final rawThemeTags =
        (data['themeTags'] as List?)?.cast<Object?>() ?? const <Object?>[];
    final rawSecondaryThemes =
        (data['secondaryThemes'] as List?)?.cast<Object?>() ??
        const <Object?>[];
    final primaryTheme = (data['primaryTheme'] ?? '').toString().trim();
    final tags = <String>[
      for (final item in rawTags) item.toString().trim(),
      if (rawTags.isEmpty) ...<String>[
        for (final item in rawThemeTags) item.toString().trim(),
        if (primaryTheme.isNotEmpty) primaryTheme,
        for (final item in rawSecondaryThemes) item.toString().trim(),
      ],
    ].where((item) => item.isNotEmpty).toSet().take(3).toList(growable: false);
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
      'tags': tags,
      'createdAt': data['createdAt'] ?? fallbackUpdatedAt ?? now,
      'updatedAt': data['updatedAt'] ?? fallbackUpdatedAt ?? now,
      'role': (data['role'] ?? 'owner').toString(),
      'joinStatus': (data['joinStatus'] ?? 'joined').toString(),
      'isFollowed': data['isFollowed'] as bool? ?? true,
    };
  }

  static Map<String, dynamic> normalizedCircleGroup(
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
      'name': (data['name'] ?? '未命名讨论').toString(),
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

  static bool _postBelongsToCircle(Map<String, dynamic> row, String circleId) {
    final primaryId = (row['circleId'] ?? '').toString().trim();
    if (primaryId == circleId) {
      return true;
    }
    return stringList(row['circleIds']).contains(circleId);
  }
}
