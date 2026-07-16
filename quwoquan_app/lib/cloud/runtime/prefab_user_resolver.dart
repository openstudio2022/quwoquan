import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/user/generated/prefab_user_metadata.g.dart';

/// 创作者规模 fixture 身份解析器。
class PrefabUserResolver {
  PrefabUserResolver._();

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
    return PrefabUserMetadata.currentSubAccountId;
  }

  static String get currentUserVariantUserId {
    return PrefabUserMetadata.currentUserId;
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
    if (subAccountId == 'me') {
      return true;
    }
    return isCurrentUserVariantId(subAccountId);
  }

  static Map<String, Map<String, dynamic>> _creatorIndex() {
    final users = (_creatorSlice()['users'] as List<dynamic>? ?? const []);
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

  static Map<String, dynamic> _creatorSlice() {
    return _creatorSliceCache ??= _readRequiredFixtureJson(
      '_shared/test_fixtures/user_pool.creator_pool.travel_photo_1k_v1.json',
    );
  }

  static Map<String, dynamic> _readRequiredFixtureJson(String relativePath) {
    final value = ContractFixtureRuntimeLoader.metadataJson(relativePath);
    if (value == null) {
      throw StateError('missing contract fixture: $relativePath');
    }
    return value;
  }
}
