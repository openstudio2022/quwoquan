import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';

/// 预制用户双轨 resolver：creator_pool 优先，archive alias 兼容。
class PrefabUserResolver {
  PrefabUserResolver._();

  static Map<String, dynamic>? _manifestCache;
  static Map<String, dynamic>? _creatorSliceCache;

  static String resolveUserId(String userId) {
    final normalized = userId;
    final creator = _creatorIndex();
    if (creator.containsKey(normalized)) {
      return creator[normalized]!['userId'] as String? ?? normalized;
    }
    return normalized;
  }

  static String resolveSubAccountId(String subAccountId) {
    final normalized = subAccountId;
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
    return 'fixture_sub_current';
  }

  static String get currentUserVariantUserId {
    final slot = _manifest()?['currentUserVariant'] as Map<String, dynamic>?;
    final userId = slot?['userId'] as String?;
    if (userId != null && userId.isNotEmpty) {
      return userId;
    }
    return 'fixture_user_current';
  }

  static Map<String, dynamic>? creatorProfileWireFor(String id) {
    final normalized = id;
    final entry = _creatorIndex()[normalized] ?? _creatorIndex()[id];
    if (entry == null) {
      return null;
    }
    final userId = entry['userId']?.toString() ?? normalized;
    final subAccountId =
        entry['subAccountId']?.toString() ??
        ((entry['subAccountRefs'] as List<dynamic>?)?.first?.toString()) ??
        userId;
    final avatarKey = _mediaObjectKey(entry, 'avatar');
    final backgroundKey = _mediaObjectKey(entry, 'cover');
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
      'backgroundUrl': backgroundKey,
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
        id == currentUserVariantSubAccountId;
  }

  static bool isOwnerLikeSubAccountId(String subAccountId) {
    const archiveOwnerLike = {'me', 'fixture_user_current'};
    if (archiveOwnerLike.contains(subAccountId)) {
      return true;
    }
    return isCurrentUserVariantId(subAccountId);
  }

  static Map<String, Map<String, dynamic>> _creatorIndex() {
    final users = (_creatorSlice()?['users'] as List<dynamic>? ?? const []);
    final index = <String, Map<String, dynamic>>{};
    for (final raw in users) {
      if (raw is! Map<String, dynamic>) continue;
      final userId = raw['userId']?.toString();
      final subAccountId =
          raw['subAccountId']?.toString() ??
          ((raw['subAccountRefs'] as List<dynamic>?)?.first?.toString());
      if (userId != null) index[userId] = raw;
      if (subAccountId != null) index[subAccountId] = raw;
    }
    return index;
  }

  static String _mediaObjectKey(Map<String, dynamic> entry, String kind) {
    final direct = kind == 'avatar'
        ? entry['avatarObjectKey']?.toString()
        : entry['backgroundObjectKey']?.toString();
    if (direct != null && direct.isNotEmpty) {
      return direct;
    }
    final media = kind == 'avatar'
        ? entry['avatarMedia']
        : entry['backgroundMedia'];
    if (media is Map<String, dynamic>) {
      final objectKey = media['objectKey']?.toString() ?? '';
      if (objectKey.isNotEmpty) {
        return objectKey;
      }
    }
    return '';
  }

  static Map<String, dynamic>? _manifest() {
    return _manifestCache ??= _readFixtureJson(
      '_shared/test_fixtures/user_pool.manifest.travel_photo_1k_v1.json',
    );
  }

  static Map<String, dynamic>? _creatorSlice() {
    return _creatorSliceCache ??= _readFixtureJson(
      '_shared/test_fixtures/user_pool.creator_pool.travel_photo_1k_v1.json',
    );
  }

  static Map<String, dynamic>? _readFixtureJson(String relativePath) {
    return ContractFixtureRuntimeLoader.metadataJson(relativePath);
  }
}
