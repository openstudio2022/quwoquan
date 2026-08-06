import '../../../../runtime/fixtures/object_scenario_seed_reader.dart';

/// 仅供 local_contract 使用的用户身份与资料索引。
///
/// 数据通过 [ObjectScenarioSeedReader] 从 user-service canonical 场景按需读取，
/// 不生成或编译 App fixture bundle。
final class FixtureUserResolver {
  FixtureUserResolver._();

  static final Map<String, Map<String, dynamic>> _userIndex = _buildUserIndex();

  static String get currentUserVariantUserId =>
      _currentUser['userId'] as String;

  static String get currentUserVariantPersonaId =>
      _personaId(_currentUser) ?? currentUserVariantUserId;

  static String resolveUserId(String userId) {
    final normalized = userId.trim();
    return _userIndex[normalized]?['userId'] as String? ?? normalized;
  }

  static String resolvePersonaId(String personaId) {
    final normalized = personaId.trim();
    return _personaId(_userIndex[normalized] ?? const <String, dynamic>{}) ??
        normalized;
  }

  static Map<String, dynamic>? profileWireFor(String id) {
    final entry = _userIndex[id.trim()];
    if (entry == null) {
      return null;
    }
    final userId = entry['userId'] as String? ?? id.trim();
    final personaId = _personaId(entry) ?? userId;
    final avatarKey = _mediaObjectKey(entry, 'avatar');
    final backgroundKey = _mediaObjectKey(entry, 'background');
    return <String, dynamic>{
      'personaId': personaId,
      'ownerUserId': userId,
      'subjectType': 'account',
      'userHandle': entry['userHandle']?.toString() ?? userId,
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
    return id == currentUserVariantUserId || id == currentUserVariantPersonaId;
  }

  static bool isOwnerLikePersonaId(String personaId) {
    return personaId == 'me' || isCurrentUserVariantId(personaId);
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
      final personaId = _personaId(entry);
      if (personaId != null) {
        index[personaId] = entry;
      }
    }
    return Map<String, Map<String, dynamic>>.unmodifiable(index);
  }

  static String? _personaId(Map<String, dynamic> entry) {
    final explicitId = entry['personaId']?.toString().trim();
    if (explicitId != null && explicitId.isNotEmpty) {
      return explicitId;
    }
    final refs = entry['personaRefs'];
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
