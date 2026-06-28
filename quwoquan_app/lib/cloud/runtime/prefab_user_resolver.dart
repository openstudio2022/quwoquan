import 'dart:convert';
import 'dart:io';

/// 预制用户双轨 resolver：creator_pool 优先，legacy alias 兼容。
class PrefabUserResolver {
  PrefabUserResolver._();

  static Map<String, dynamic>? _manifestCache;
  static Map<String, dynamic>? _creatorSliceCache;
  static Map<String, String>? _aliasCache;

  static String resolveUserId(String userId) {
    final normalized = _legacyAliases()[userId] ?? userId;
    final creator = _creatorIndex();
    if (creator.containsKey(normalized)) {
      return creator[normalized]!['userId'] as String? ?? normalized;
    }
    return normalized;
  }

  static String resolveSubAccountId(String subAccountId) {
    final normalized = _legacyAliases()[subAccountId] ?? subAccountId;
    final creator = _creatorIndex();
    if (creator.containsKey(normalized)) {
      return creator[normalized]!['subAccountId'] as String? ?? normalized;
    }
    return subAccountId;
  }

  static String get currentUserVariantSubAccountId {
    final slot = _manifest()?['currentUserVariant'] as Map<String, dynamic>?;
    final sub = slot?['subAccountId'] as String?;
    if (sub != null && sub.isNotEmpty) {
      return sub;
    }
    return 'agent_sub_account_travel_current_user_variant';
  }

  static String get currentUserVariantUserId {
    final slot = _manifest()?['currentUserVariant'] as Map<String, dynamic>?;
    final userId = slot?['userId'] as String?;
    if (userId != null && userId.isNotEmpty) {
      return userId;
    }
    return 'qwq_creator_current_user_variant';
  }

  static Map<String, dynamic>? creatorProfileWireFor(String id) {
    final normalized = _legacyAliases()[id] ?? id;
    final entry = _creatorIndex()[normalized] ?? _creatorIndex()[id];
    if (entry == null) {
      return null;
    }
    final userId = entry['userId']?.toString() ?? normalized;
    final subAccountId = entry['subAccountId']?.toString() ??
        ((entry['subAccountRefs'] as List<dynamic>?)?.first?.toString()) ??
        userId;
    final avatarKey = entry['avatarObjectKey']?.toString() ?? '';
    return <String, dynamic>{
      'subAccountId': subAccountId,
      'ownerUserId': userId,
      'subjectType': 'user',
      'userHandle': entry['userHandle']?.toString() ?? userId,
      'username': entry['userHandle']?.toString() ?? userId,
      'displayName': entry['displayName']?.toString() ?? userId,
      'nickname': entry['displayName']?.toString() ?? userId,
      'avatarUrl': avatarKey.isEmpty ? '' : avatarKey,
      'avatarVersion': 1,
      'backgroundUrl': entry['backgroundObjectKey']?.toString() ?? '',
      'bio': entry['bio']?.toString() ?? '',
      'identityTags': (entry['tags'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
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
        id == currentUserVariantSubAccountId ||
        _legacyAliases().containsKey(id);
  }

  static bool isOwnerLikeSubAccountId(String subAccountId) {
    const legacyOwnerLike = {'me', 'fixture_user_current', 'user_001'};
    if (legacyOwnerLike.contains(subAccountId)) {
      return true;
    }
    return isCurrentUserVariantId(subAccountId);
  }

  static Map<String, String> _legacyAliases() {
    return _aliasCache ??= () {
      final slot = _manifest()?['currentUserVariant'] as Map<String, dynamic>?;
      final target = slot?['userId'] as String? ?? 'qwq_creator_current_user_variant';
      final aliases = (slot?['legacyAliases'] as List<dynamic>? ?? const ['fixture_user_current', 'user_001'])
          .map((e) => e.toString())
          .toList();
      return {for (final alias in aliases) alias: target};
    }();
  }

  static Map<String, Map<String, dynamic>> _creatorIndex() {
    final users = (_creatorSlice()?['users'] as List<dynamic>? ?? const []);
    final index = <String, Map<String, dynamic>>{};
    for (final raw in users) {
      if (raw is! Map<String, dynamic>) continue;
      final userId = raw['userId']?.toString();
      final subAccountId = raw['subAccountId']?.toString() ??
          ((raw['subAccountRefs'] as List<dynamic>?)?.first?.toString());
      final authorId = raw['authorId']?.toString();
      if (userId != null) index[userId] = raw;
      if (subAccountId != null) index[subAccountId] = raw;
      if (authorId != null) index[authorId] = raw;
    }
    return index;
  }

  static Map<String, dynamic>? _manifest() {
    return _manifestCache ??= _readFixtureJson(
      '_shared/test_fixtures/user_pool.manifest.json',
    );
  }

  static Map<String, dynamic>? _creatorSlice() {
    return _creatorSliceCache ??= _readFixtureJson(
      '_shared/test_fixtures/user_pool.creator_pool.json',
    );
  }

  static Map<String, dynamic>? _readFixtureJson(String relativePath) {
    for (final root in _metadataRoots()) {
      final file = File('$root/$relativePath');
      if (file.existsSync()) {
        return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      }
    }
    return null;
  }

  static Iterable<String> _metadataRoots() sync* {
    final fromEnv = Platform.environment['QWQ_REPO_ROOT'];
    if (fromEnv != null && fromEnv.isNotEmpty) {
      yield '$fromEnv/quwoquan_service/contracts/metadata';
    }
    var dir = Directory.current;
    for (var i = 0; i < 8; i++) {
      final candidate = '${dir.path}/quwoquan_service/contracts/metadata';
      if (Directory(candidate).existsSync()) {
        yield candidate;
        return;
      }
      dir = dir.parent;
    }
  }
}
