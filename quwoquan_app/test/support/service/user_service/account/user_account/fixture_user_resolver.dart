import 'user_profile_test_builder.dart';

/// 仅供 user_account local_contract 使用的用户身份与资料索引。
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
    if (entry == null) return null;
    final userId = entry['userId'] as String? ?? id.trim();
    final personaId = _personaId(entry) ?? userId;
    return <String, dynamic>{
      'personaId': personaId,
      'ownerUserId': userId,
      'subjectType': 'account',
      'userHandle': entry['userHandle']?.toString() ?? userId,
      'displayName': entry['displayName']?.toString() ?? userId,
      'nickname': entry['displayName']?.toString() ?? userId,
      'avatarUrl': entry['avatarObjectKey']?.toString() ?? '',
      'avatarVersion': entry['avatarVersion'] ?? 1,
      'backgroundUrl': entry['backgroundObjectKey']?.toString() ?? '',
      'bio': entry['bio']?.toString() ?? '',
      'identityTags': (entry['tags'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(growable: false),
      'followerCount': entry['followerCount'] ?? 0,
      'followingCount': entry['followingCount'] ?? 0,
      'postCount': entry['postCount'] ?? 0,
      'circleCount': entry['circleCount'] ?? 0,
      'likeCount': entry['likeCount'] ?? 0,
      'isolationLevel': 'open',
      'profileVisibility': 'public',
      'inheritsFromOwner': false,
      'overriddenFields': const <String>[],
    };
  }

  static bool isCurrentUserVariantId(String id) =>
      id == currentUserVariantUserId || id == currentUserVariantPersonaId;

  static bool isOwnerLikePersonaId(String personaId) =>
      personaId == 'me' || isCurrentUserVariantId(personaId);

  static Map<String, dynamic> get _currentUser {
    for (final entry in _userIndex.values) {
      if (entry['primaryRole'] == 'currentUserVariant') return entry;
    }
    throw StateError('user_account profile builder lacks currentUserVariant');
  }

  static Map<String, Map<String, dynamic>> _buildUserIndex() {
    final index = <String, Map<String, dynamic>>{};
    for (final raw in userProfileWireExamples()) {
      final entry = raw.cast<String, dynamic>();
      final userId = entry['userId']?.toString().trim() ?? '';
      if (userId.isEmpty) continue;
      index[userId] = entry;
      final personaId = _personaId(entry);
      if (personaId != null) index[personaId] = entry;
    }
    return Map<String, Map<String, dynamic>>.unmodifiable(index);
  }

  static String? _personaId(Map<String, dynamic> entry) {
    final value = entry['personaId']?.toString().trim() ?? '';
    return value.isEmpty ? null : value;
  }
}
