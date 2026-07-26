part of '../../alpha_user_profile_repository.dart';

Map<String, dynamic> _defaultProfile(String userId) {
  const profileNames = <String, String>{
    'user_001': '趣我圈用户',
    'nature_photographer': '自然摄影师',
    'travel_photographer': '旅行摄影师',
    'street_photo': '街头摄影',
  };
  final contractProfile = _contractProfileRowByUserId(userId);
  final displayName =
      profileNames[userId] ??
      contractProfile?['displayName']?.toString().trim() ??
      userId;
  return <String, dynamic>{
    'subAccountId': userId,
    'ownerUserId': userId,
    'subjectType': 'user',
    'userHandle': userId,
    'username': userId,
    'displayName': displayName,
    'nickname': displayName,
    'avatarUrl': contractProfile?['avatarUrl']?.toString() ?? '',
    'avatarVersion': 1,
    'bio': '用户与影像，记录思考与生活',
    'identityTags': const <String>['AI 产品', '产品经理', '摄影', '旅行', '北京'],
    'followerCount': 1200,
    'followingCount': 284,
    'postCount': 4,
    'circleCount': 3,
    'likeCount': 1200,
    'isolationLevel': 'normal',
    'profileVisibility': 'public',
    'inheritsFromOwner': false,
    'overriddenFields': const <String>[],
  };
}

Map<String, dynamic> _mockSocialRelationWire({required bool isFollowing}) {
  final relationState = isFollowing ? 'following' : 'followed_by';
  return <String, dynamic>{
    'subAccountId': 'u1',
    'userId': 'u1',
    'username': 'u1',
    'userHandle': 'u1',
    'displayName': '你的皮炎有点辣',
    'nickname': '你的皮炎有点辣',
    'avatarUrl':
        'media/avatar/s/mock/seed/u_1599566150163-29194dcaad36/v1/avatar.jpg',
    'avatarVersion': 1,
    'profileVisibility': 'public',
    'relationState': relationState,
    'followedAt': '2025-12-21T08:00:00Z',
    'relationshipCapability': <String, dynamic>{
      'viewerSubAccountId': kMockCurrentSubAccountId,
      'targetSubAccountId': 'u1',
      'relationState': relationState,
      'canFollow': !isFollowing,
      'canUnfollow': isFollowing,
      'canFollowBack': !isFollowing,
      'canSendMessage': isFollowing,
      'hasFormalConversation': isFollowing,
      'canOpenConversation': isFollowing,
    },
  };
}

List<Map<String, dynamic>> _mockFollowingWiresFor(String userId) {
  if (_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  return <Map<String, dynamic>>[_mockSocialRelationWire(isFollowing: true)];
}

List<Map<String, dynamic>> _mockFollowerWiresFor(String userId) {
  if (_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  return <Map<String, dynamic>>[_mockSocialRelationWire(isFollowing: false)];
}

List<Map<String, dynamic>> _contractProfileRows() {
  final seed = alphaFixtureSeedReader.userSeedSet('user_profile_core');
  final profiles = seed?['profiles'];
  if (profiles is! List) {
    return const <Map<String, dynamic>>[];
  }
  return profiles
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .toList(growable: false);
}

List<Map<String, dynamic>> _contractRelationshipRows() {
  final seed = alphaFixtureSeedReader.userSeedSet('relationship_core');
  final relationships = seed?['relationships'];
  if (relationships is! List) {
    return const <Map<String, dynamic>>[];
  }
  return relationships
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .toList(growable: false);
}

Map<String, dynamic> _contractProfileWire(Map<String, dynamic> item) {
  final stats =
      (item['stats'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final userId = item['userId'].toString();
  return <String, dynamic>{
    'subAccountId': userId,
    'ownerUserId': userId,
    'subjectType': 'user',
    'userHandle': userId,
    'username': userId,
    'displayName': item['displayName']?.toString() ?? userId,
    'nickname': item['displayName']?.toString() ?? userId,
    'avatarUrl': item['avatarUrl']?.toString() ?? '',
    'avatarVersion': (item['avatarVersion'] as num?)?.toInt() ?? 0,
    'backgroundUrl': item['backgroundUrl']?.toString() ?? '',
    'bio': item['bio']?.toString() ?? '',
    'identityTags':
        (item['identityTags'] as List?)
            ?.map((e) => e.toString())
            .toList(growable: false) ??
        const <String>[],
    'verified': item['verified'] == true,
    'followerCount': (stats['followerCount'] as num?)?.toInt() ?? 0,
    'followingCount': (stats['followingCount'] as num?)?.toInt() ?? 0,
    'postCount': (stats['postCount'] as num?)?.toInt() ?? 0,
    'circleCount': (stats['circleCount'] as num?)?.toInt() ?? 0,
    'likeCount': (stats['likeCount'] as num?)?.toInt() ?? 0,
    'isolationLevel': 'normal',
    'profileVisibility': 'public',
    'inheritsFromOwner': false,
    'overriddenFields': const <String>[],
  };
}

final Map<String, SubAccountProfileWireDto> _contractProfileWireByUserId = {
  for (final item in _contractProfileRows())
    item['userId'].toString(): SubAccountProfileWireDto.fromMap(
      _contractProfileWire(item),
    ),
};

bool _isContractFixtureUser(String userId) {
  return _contractProfileWireByUserId.containsKey(userId);
}

Map<String, dynamic>? _contractProfileRowByUserId(String userId) {
  for (final row in _contractProfileRows()) {
    if (row['userId']?.toString() == userId) {
      return row;
    }
  }
  return null;
}

Map<String, dynamic> _relationshipRowToSocialRelationWire(
  Map<String, dynamic> relationship, {
  required String relationState,
}) {
  final targetUserId = relationship['targetUserId']?.toString() ?? '';
  final sourceUserId = relationship['sourceUserId']?.toString() ?? '';
  final subAccountId = targetUserId.isNotEmpty ? targetUserId : sourceUserId;
  final profileRow =
      _contractProfileRowByUserId(targetUserId) ??
      _contractProfileRowByUserId(sourceUserId);
  final displayName =
      profileRow?['displayName']?.toString() ??
      (targetUserId.isNotEmpty ? targetUserId : sourceUserId);
  final avatarUrl = profileRow?['avatarUrl']?.toString() ?? '';
  final userHandle = profileRow?['userHandle']?.toString() ?? subAccountId;
  final username = profileRow?['username']?.toString() ?? subAccountId;
  final mutual = relationState == 'mutual';
  final following = relationState == 'following' || mutual;
  final followedBy = relationState == 'followed_by' || mutual;
  return <String, dynamic>{
    'subAccountId': subAccountId,
    'userId': subAccountId,
    'username': username,
    'userHandle': userHandle,
    'displayName': displayName,
    'nickname': displayName,
    'avatarUrl': avatarUrl,
    'avatarVersion': (profileRow?['avatarVersion'] as num?)?.toInt() ?? 0,
    'profileVisibility':
        profileRow?['profileVisibility']?.toString() ?? 'public',
    'relationState': relationState,
    'followedAt': relationship['followedAt'] ?? '2025-12-21T08:00:00Z',
    'relationshipCapability': <String, dynamic>{
      'viewerSubAccountId': kMockCurrentSubAccountId,
      'targetSubAccountId': subAccountId,
      'relationState': relationState,
      'canFollow':
          relationState == 'not_following' || relationState == 'followed_by',
      'canUnfollow': following,
      'canFollowBack': followedBy && !following,
      'canSendMessage': following,
      'hasFormalConversation': following,
      'canOpenConversation': following,
    },
  };
}

List<Map<String, dynamic>> _contractFollowingWiresFor(String userId) {
  if (!_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  return _contractRelationshipRows()
      .where(
        (row) =>
            row['sourceUserId']?.toString() == userId &&
            row['following'] == true,
      )
      .map(
        (row) => _relationshipRowToSocialRelationWire(
          row,
          relationState: row['mutualFollow'] == true ? 'mutual' : 'following',
        ),
      )
      .toList(growable: false);
}

List<Map<String, dynamic>> _contractFollowerWiresFor(String userId) {
  if (!_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  return _contractRelationshipRows()
      .where(
        (row) =>
            row['targetUserId']?.toString() == userId &&
            row['following'] == true,
      )
      .map(
        (row) => _relationshipRowToSocialRelationWire(
          <String, dynamic>{...row, 'targetUserId': row['sourceUserId']},
          relationState: row['mutualFollow'] == true ? 'mutual' : 'followed_by',
        ),
      )
      .toList(growable: false);
}

List<Map<String, dynamic>> _contractPersonaRows() {
  final seed = alphaFixtureSeedReader.userSeedSet('persona_core');
  final personas = seed?['personas'];
  if (personas is! List) {
    return const <Map<String, dynamic>>[];
  }
  final activeSubAccountId = seed?['activeSubAccountId']?.toString() ?? '';
  return personas
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .map((item) {
        final subAccountId = item['subAccountId']?.toString() ?? '';
        return <String, dynamic>{
          'subAccountId': subAccountId,
          'displayName': item['displayName']?.toString() ?? subAccountId,
          'avatarUrl':
              _contractProfileWireByUserId[subAccountId]
                      ?.avatarUrl
                      .isNotEmpty ==
                  true
              ? _contractProfileWireByUserId[subAccountId]!.avatarUrl
              : null,
          'avatarVersion':
              _contractProfileWireByUserId[subAccountId]?.avatarVersion ?? 0,
          'isPrimary': subAccountId == activeSubAccountId,
          'isPrivate': false,
          'isActive': subAccountId == activeSubAccountId,
          'createdAt': '',
          'updatedAt': '',
        };
      })
      .toList(growable: false);
}
