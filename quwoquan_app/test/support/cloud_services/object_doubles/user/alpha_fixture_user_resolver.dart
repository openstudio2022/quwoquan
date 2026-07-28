import '../object_scenario_seed_reader.dart';

/// 仅供 local_contract 使用的用户身份与资料索引。
///
/// 数据通过 [ObjectScenarioSeedReader] 从 user-service canonical 场景按需读取，
/// 不生成或编译 App fixture bundle。
final class AlphaFixtureUserResolver {
  AlphaFixtureUserResolver._();

  static final Map<String, Map<String, dynamic>> _userIndex = _buildUserIndex();

  static String get currentUserVariantUserId =>
      _currentUser['userId'] as String;

  static String get currentUserVariantSubAccountId =>
      _subAccountId(_currentUser) ?? currentUserVariantUserId;

  static String resolveUserId(String userId) {
    final normalized = userId.trim();
    return _userIndex[normalized]?['userId'] as String? ?? normalized;
  }

  static String resolveSubAccountId(String subAccountId) {
    final normalized = subAccountId.trim();
    return _subAccountId(_userIndex[normalized] ?? const <String, dynamic>{}) ??
        normalized;
  }

  static Map<String, dynamic>? profileWireFor(String id) {
    final entry = _userIndex[id.trim()];
    if (entry == null) {
      return null;
    }
    final userId = entry['userId'] as String? ?? id.trim();
    final subAccountId = _subAccountId(entry) ?? userId;
    final avatarKey = _mediaObjectKey(entry, 'avatar');
    final backgroundKey = _mediaObjectKey(entry, 'background');
    return <String, dynamic>{
      'subAccountId': subAccountId,
      'ownerUserId': userId,
      'subjectType': 'user',
      'userHandle': entry['userHandle']?.toString() ?? userId,
      'username': entry['userHandle']?.toString() ?? userId,
      'displayName': entry['displayName']?.toString() ?? userId,
      'nickname': entry['displayName']?.toString() ?? userId,
      'avatarUrl': avatarKey,
      'avatarVersion': 1,
      'backgroundUrl': backgroundKey,
      'bio': entry['bio']?.toString() ?? '',
      'identityTags': (entry['tags'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(growable: false),
      'followerCount': 0,
      'followingCount': 0,
      'postCount': 0,
      'circleCount': 0,
      'likeCount': 0,
      'isolationLevel': 'open',
      'profileVisibility': 'public',
      'inheritsFromOwner': false,
      'overriddenFields': const <String>[],
    };
  }

  static bool isCurrentUserVariantId(String id) {
    return id == currentUserVariantUserId ||
        id == currentUserVariantSubAccountId;
  }

  static bool isOwnerLikeSubAccountId(String subAccountId) {
    return subAccountId == 'me' || isCurrentUserVariantId(subAccountId);
  }

  static Map<String, dynamic> get _currentUser {
    for (final entry in _userIndex.values) {
      if (entry['primaryRole'] == 'currentUserVariant') {
        return entry;
      }
    }
    throw StateError(
      'alpha fixture user_profile_core lacks currentUserVariant',
    );
  }

  static Map<String, Map<String, dynamic>> _buildUserIndex() {
    final profiles = objectScenarioSeedReader.requireSeedSet(
      'user',
      'user_profile_core',
    )['profiles'];
    if (profiles is! List) {
      throw const FormatException(
        'user/user_profile_core.profiles must be an array',
      );
    }
    final index = <String, Map<String, dynamic>>{};
    for (final raw in profiles) {
      if (raw is! Map) {
        continue;
      }
      final entry = raw.map((key, value) => MapEntry(key.toString(), value));
      final userId = entry['userId']?.toString().trim();
      if (userId == null || userId.isEmpty) {
        continue;
      }
      index[userId] = entry;
      final subAccountId = _subAccountId(entry);
      if (subAccountId != null) {
        index[subAccountId] = entry;
      }
    }
    return Map<String, Map<String, dynamic>>.unmodifiable(index);
  }

  static String? _subAccountId(Map<String, dynamic> entry) {
    final explicitId = entry['subAccountId']?.toString().trim();
    if (explicitId != null && explicitId.isNotEmpty) {
      return explicitId;
    }
    final refs = entry['subAccountRefs'];
    if (refs is List && refs.isNotEmpty) {
      final firstRef = refs.first.toString().trim();
      if (firstRef.isNotEmpty) {
        return firstRef;
      }
    }
    return null;
  }

  static String _mediaObjectKey(Map<String, dynamic> entry, String kind) {
    final directKey = kind == 'avatar'
        ? entry['avatarObjectKey']?.toString()
        : entry['backgroundObjectKey']?.toString();
    if (directKey != null && directKey.isNotEmpty) {
      return directKey;
    }
    final media = entry['media'];
    if (media is Map) {
      final descriptor = media[kind];
      if (descriptor is Map) {
        return descriptor['objectKey']?.toString() ?? '';
      }
    }
    return kind == 'avatar' ? entry['avatarUrl']?.toString() ?? '' : '';
  }
}
