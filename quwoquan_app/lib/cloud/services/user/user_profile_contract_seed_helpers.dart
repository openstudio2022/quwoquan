part of 'user_profile_repository.dart';

Map<String, dynamic> _defaultProfile(String userId) {
  const profileNames = <String, String>{
    'user_001': '趣我圈用户',
    'nature_photographer': '自然摄影师',
    'travel_photographer': '旅行摄影师',
    'street_photo': '街头摄影',
  };
  final chatName = profileNames[userId] ?? ChatMockData.nameFor(userId);
  return <String, dynamic>{
    'subAccountId': userId,
    'ownerUserId': userId,
    'subjectType': 'user',
    'userHandle': userId,
    'username': userId,
    'displayName': chatName.isEmpty ? userId : chatName,
    'nickname': chatName.isEmpty ? userId : chatName,
    'avatarUrl': ChatMockData.avatarFor(userId) ?? '',
    'bio': '',
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
  return <String, dynamic>{
    'subAccountId': 'u1',
    'userId': 'u1',
    'displayName': '你的皮炎有点辣',
    'nickname': '你的皮炎有点辣',
    'avatarUrl':
        'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
    'isFollowing': isFollowing,
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

List<Map<String, dynamic>> _mockInteractionReceivedWiresFor(String userId) {
  if (_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  return <Map<String, dynamic>>[
    <String, dynamic>{
      'activityId': 'mock-like-u1-${userId}_p1',
      'activityType': 'like',
      'direction': 'received',
      'actorSubAccountId': 'u1',
      'actorDisplayName': '你的皮炎有点辣',
      'actorAvatarUrl':
          'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      'targetSubAccountId': userId,
      'targetContentId': '${userId}_p1',
      'targetContentType': 'photo',
      'targetContentSummary': '光影的节奏',
      'createdAt': '2025-12-21T09:30:00Z',
    },
  ];
}

List<Map<String, dynamic>> _mockInteractionSentWiresFor(String userId) {
  if (_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  return <Map<String, dynamic>>[
    <String, dynamic>{
      'activityId': 'mock-comment-$userId-u1',
      'activityType': 'comment',
      'direction': 'sent',
      'actorSubAccountId': userId,
      'actorDisplayName': _defaultProfile(userId)['displayName'],
      'actorAvatarUrl': _defaultProfile(userId)['avatarUrl'],
      'targetSubAccountId': 'u1',
      'targetContentId': 'u1_p1',
      'targetContentType': 'photo',
      'targetContentSummary': '光影的节奏',
      'createdAt': '2025-12-21T10:00:00Z',
    },
  ];
}

List<Map<String, dynamic>> _contractProfileRows() {
  final seed = ContractFixtureRuntimeLoader.userSeedSet('user_profile_core');
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
  final seed = ContractFixtureRuntimeLoader.userSeedSet('relationship_core');
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
    'backgroundUrl': item['backgroundUrl']?.toString() ?? '',
    'bio': item['bio']?.toString() ?? '',
    'identityTags': (item['identityTags'] as List?)
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
  required bool isFollowing,
}) {
  final targetUserId = relationship['targetUserId']?.toString() ?? '';
  final sourceUserId = relationship['sourceUserId']?.toString() ?? '';
  final profileRow =
      _contractProfileRowByUserId(targetUserId) ??
      _contractProfileRowByUserId(sourceUserId);
  final displayName =
      profileRow?['displayName']?.toString() ??
      (targetUserId.isNotEmpty ? targetUserId : sourceUserId);
  final avatarUrl = profileRow?['avatarUrl']?.toString() ?? '';
  return <String, dynamic>{
    'subAccountId': targetUserId.isNotEmpty ? targetUserId : sourceUserId,
    'userId': targetUserId.isNotEmpty ? targetUserId : sourceUserId,
    'displayName': displayName,
    'nickname': displayName,
    'avatarUrl': avatarUrl,
    'isFollowing': isFollowing,
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
        (row) => _relationshipRowToSocialRelationWire(row, isFollowing: true),
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
        (row) => _relationshipRowToSocialRelationWire(<String, dynamic>{
          ...row,
          'targetUserId': row['sourceUserId'],
        }, isFollowing: row['mutualFollow'] == true),
      )
      .toList(growable: false);
}

List<Map<String, dynamic>> _contentSeedPosts() {
  final contentSeed = ContractFixtureRuntimeLoader.contentSeedSet();
  final posts = contentSeed?['posts'];
  if (posts is! List) {
    return const <Map<String, dynamic>>[];
  }
  return posts
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .toList(growable: false);
}

List<Map<String, dynamic>> _contentSeedComments() {
  final contentSeed = ContractFixtureRuntimeLoader.contentSeedSet();
  final comments = contentSeed?['comments'];
  if (comments is! List) {
    return const <Map<String, dynamic>>[];
  }
  return comments
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .toList(growable: false);
}

List<Map<String, dynamic>> _contentSeedReactions() {
  final contentSeed = ContractFixtureRuntimeLoader.contentSeedSet();
  final reactions = contentSeed?['reactions'];
  if (reactions is! List) {
    return const <Map<String, dynamic>>[];
  }
  return reactions
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .toList(growable: false);
}

List<Map<String, dynamic>> _contractLikeWiresFor(String userId) {
  if (!_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  final postsById = <String, Map<String, dynamic>>{
    for (final post in _contentSeedPosts())
      (post['postId'] ?? post['id']).toString(): post,
  };
  final profileById = <String, Map<String, dynamic>>{
    for (final row in _contractProfileRows()) row['userId'].toString(): row,
  };
  return _contentSeedReactions()
      .where((reaction) => reaction['liked'] == true)
      .map((reaction) {
        final likerUserId = reaction['userId']?.toString() ?? '';
        final postId = reaction['postId']?.toString() ?? '';
        final post = postsById[postId];
        if (post == null || post['authorId']?.toString() != userId) {
          return null;
        }
        final likerProfile = profileById[likerUserId];
        return <String, dynamic>{
          'postId': postId,
          'title':
              post['title']?.toString() ?? post['body']?.toString() ?? postId,
          'coverUrl':
              post['coverUrl']?.toString() ??
              post['thumbnailUrl']?.toString() ??
              '',
          'likerNickname':
              likerProfile?['displayName']?.toString() ?? likerUserId,
          'likerAvatarUrl': likerProfile?['avatarUrl']?.toString() ?? '',
        };
      })
      .whereType<Map<String, dynamic>>()
      .toList(growable: false);
}

List<Map<String, dynamic>> _contractInteractionReceivedWiresFor(String userId) {
  if (!_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  final postsById = <String, Map<String, dynamic>>{
    for (final post in _contentSeedPosts())
      (post['postId'] ?? post['id']).toString(): post,
  };
  final profileById = <String, Map<String, dynamic>>{
    for (final row in _contractProfileRows()) row['userId'].toString(): row,
  };
  final likes = _contentSeedReactions()
      .where((reaction) => reaction['liked'] == true)
      .map((reaction) {
        final postId = reaction['postId']?.toString() ?? '';
        final actorId = reaction['userId']?.toString() ?? '';
        final post = postsById[postId];
        if (post == null || post['authorId']?.toString() != userId) {
          return null;
        }
        final actorProfile = profileById[actorId];
        return <String, dynamic>{
          'activityId': 'like:$actorId:$postId',
          'activityType': 'like',
          'direction': 'received',
          'actorSubAccountId': actorId,
          'actorDisplayName':
              actorProfile?['displayName']?.toString() ?? actorId,
          'actorAvatarUrl': actorProfile?['avatarUrl']?.toString() ?? '',
          'targetSubAccountId': userId,
          'targetContentId': postId,
          'targetContentType':
              post['contentType']?.toString() ?? post['type']?.toString() ?? '',
          'targetContentSummary':
              post['title']?.toString() ?? post['body']?.toString() ?? '',
        };
      })
      .whereType<Map<String, dynamic>>();
  final comments = _contentSeedComments().map((comment) {
    final postId = comment['postId']?.toString() ?? '';
    final actorId = comment['authorId']?.toString() ?? '';
    final post = postsById[postId];
    if (post == null || post['authorId']?.toString() != userId) {
      return null;
    }
    return <String, dynamic>{
      'activityId':
          comment['commentId']?.toString() ?? 'comment:$actorId:$postId',
      'activityType': 'comment',
      'direction': 'received',
      'actorSubAccountId': actorId,
      'actorDisplayName':
          comment['authorDisplayNameSnapshot']?.toString() ?? actorId,
      'actorAvatarUrl': comment['authorAvatarUrlSnapshot']?.toString() ?? '',
      'targetSubAccountId': userId,
      'targetContentId': postId,
      'targetContentType':
          post['contentType']?.toString() ?? post['type']?.toString() ?? '',
      'targetContentSummary': comment['content']?.toString() ?? '',
      'createdAt': comment['createdAt'],
    };
  }).whereType<Map<String, dynamic>>();
  return <Map<String, dynamic>>[...likes, ...comments];
}

List<Map<String, dynamic>> _contractInteractionSentWiresFor(String userId) {
  if (!_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  final postsById = <String, Map<String, dynamic>>{
    for (final post in _contentSeedPosts())
      (post['postId'] ?? post['id']).toString(): post,
  };
  return _contentSeedComments()
      .where((comment) => comment['authorId']?.toString() == userId)
      .map((comment) {
        final postId = comment['postId']?.toString() ?? '';
        final post = postsById[postId];
        final targetUserId = post?['authorId']?.toString() ?? '';
        return <String, dynamic>{
          'activityId':
              comment['commentId']?.toString() ?? 'comment:$userId:$postId',
          'activityType': 'comment',
          'direction': 'sent',
          'actorSubAccountId': userId,
          'actorDisplayName':
              comment['authorDisplayNameSnapshot']?.toString() ?? userId,
          'actorAvatarUrl':
              comment['authorAvatarUrlSnapshot']?.toString() ?? '',
          'targetSubAccountId': targetUserId,
          'targetContentId': postId,
          'targetContentType':
              post?['contentType']?.toString() ??
              post?['type']?.toString() ??
              '',
          'targetContentSummary': comment['content']?.toString() ?? '',
          'createdAt': comment['createdAt'],
        };
      })
      .toList(growable: false);
}

List<Map<String, dynamic>> _contractPersonaRows() {
  final seed = ContractFixtureRuntimeLoader.userSeedSet('persona_core');
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
          'id': subAccountId,
          'userId': subAccountId,
          'displayName': item['name']?.toString() ?? subAccountId,
          'avatarUrl':
              _contractProfileWireByUserId[subAccountId]
                      ?.avatarUrl
                      .isNotEmpty ==
                  true
              ? _contractProfileWireByUserId[subAccountId]!.avatarUrl
              : null,
          'isPrimary': subAccountId == activeSubAccountId,
          'isPrivate': false,
          'isActive': subAccountId == activeSubAccountId,
          'createdAt': '',
          'updatedAt': '',
        };
      })
      .toList(growable: false);
}
