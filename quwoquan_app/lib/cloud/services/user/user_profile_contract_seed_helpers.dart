part of 'user_profile_repository.dart';

Map<String, dynamic> _defaultProfile(String userId) {
  final chatName = ChatMockData.nameFor(userId);
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
    'isolationLevel': 'normal',
    'profileVisibility': 'public',
    'inheritsFromOwner': false,
    'overriddenFields': const <String>[],
  };
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
