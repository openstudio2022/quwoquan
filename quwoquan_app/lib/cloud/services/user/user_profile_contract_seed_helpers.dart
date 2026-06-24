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
    'avatarUrl': ChatMockData.avatarFor(userId),
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
      'viewerSubAccountId': ChatMockData.currentUserProfileId,
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

Map<String, dynamic> _interactionWire({
  required String activityId,
  required String activityType,
  required String direction,
  required String actorSubAccountId,
  required String actorDisplayName,
  required String actorAvatarUrl,
  int actorAvatarVersion = 0,
  required String targetSubAccountId,
  required String targetContentId,
  required String targetContentType,
  required String targetContentSummary,
  required String displaySubAccountId,
  required String displayName,
  required String displayAvatarUrl,
  int displayAvatarVersion = 0,
  required String primaryText,
  required String previewMediaKind,
  required List<String> filterKeys,
  String displayUserRouteId = 'userProfile',
  String contextText = '',
  String previewImageUrl = '',
  String previewText = '',
  bool previewUnavailable = false,
  String previewObjectId = '',
  String previewRouteId = 'workBrowser',
  String commentKind = 'none',
  String commentId = '',
  String parentCommentId = '',
  Object? createdAt,
}) {
  final normalizedFilters = <String>{
    'all',
    ...filterKeys.where((key) => key.trim().isNotEmpty),
  }.toList(growable: false);
  return <String, dynamic>{
    'activityId': activityId,
    'activityType': activityType,
    'direction': direction,
    'commentKind': commentKind,
    'actorSubAccountId': actorSubAccountId,
    'actorDisplayName': actorDisplayName,
    'actorAvatarUrl': actorAvatarUrl,
    'actorAvatarVersion': actorAvatarVersion,
    'targetSubAccountId': targetSubAccountId,
    'targetContentId': targetContentId,
    'targetContentType': targetContentType,
    'targetContentSummary': targetContentSummary,
    'displaySubAccountId': displaySubAccountId,
    'displayName': displayName,
    'displayAvatarUrl': displayAvatarUrl,
    'displayAvatarVersion': displayAvatarVersion,
    'displayUserRouteId': displayUserRouteId,
    'primaryText': primaryText,
    'contextText': contextText,
    'previewMediaKind': previewMediaKind,
    'previewImageUrl': previewImageUrl,
    'previewText': previewText,
    'previewUnavailable': previewUnavailable,
    'previewObjectId': previewObjectId.isNotEmpty
        ? previewObjectId
        : targetContentId,
    'previewRouteId': previewUnavailable ? '' : previewRouteId,
    'filterKeys': normalizedFilters,
    'commentId': commentId,
    'parentCommentId': parentCommentId,
    'createdAt': createdAt,
  };
}

List<Map<String, dynamic>> _mockInteractionSentWiresFor(String userId) {
  if (_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  final defaultProfile = _defaultProfile(userId);
  final actorName = defaultProfile['displayName']?.toString() ?? userId;
  final actorAvatar = defaultProfile['avatarUrl']?.toString() ?? '';
  return <Map<String, dynamic>>[
    _interactionWire(
      activityId: 'mock-sent-like-image-$userId-u1',
      activityType: 'like',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u1',
      targetContentId: 'u1_p1',
      targetContentType: 'image',
      targetContentSummary: '光影的节奏',
      displaySubAccountId: 'u1',
      displayName: '你的皮炎有点辣',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1599566150163-29194dcaad36/v1/avatar.jpg',
      primaryText: '你点赞了TA的记录',
      previewMediaKind: 'image',
      previewImageUrl:
          'media/image/s/mock/seed/p_1647956450271-2ff54205bebf/v1/image.jpg',
      previewText: '光影的节奏',
      filterKeys: const <String>['likes'],
      createdAt: '2025-12-21T10:00:00Z',
    ),
    _interactionWire(
      activityId: 'mock-sent-view-profile-$userId-u8',
      activityType: 'view',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u8',
      targetContentId: 'u8',
      targetContentType: 'profile',
      targetContentSummary: '纸上旅行主页',
      displaySubAccountId: 'u8',
      displayName: '纸上旅行',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1685523410021-ae81127c98/v1/avatar.jpg',
      primaryText: '你看过纸上旅行的主页',
      previewMediaKind: 'text',
      previewText: '个人主页',
      previewRouteId: 'userProfile',
      filterKeys: const <String>['views'],
      createdAt: '2025-12-21T09:55:00Z',
    ),
    _interactionWire(
      activityId: 'mock-sent-like-comment-$userId-u2',
      activityType: 'like',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u2',
      targetContentId: 'u2_p1',
      targetContentType: 'comment',
      targetContentSummary: '这段路我也走过',
      displaySubAccountId: 'u2',
      displayName: '海边的风',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1679823410021-6d22f8c1f3/v1/avatar.jpg',
      primaryText: '你点赞了TA的记录',
      contextText: '这段路我也走过',
      previewMediaKind: 'video',
      previewImageUrl:
          'media/image/s/mock/seed/p_1646034296147-d8ed3aace9a4/v1/image.jpg',
      previewText: '海岸线',
      filterKeys: const <String>['likes'],
      commentKind: 'comment',
      createdAt: '2025-12-21T09:50:00Z',
    ),
    _interactionWire(
      activityId: 'mock-sent-comment-video-$userId-u3',
      activityType: 'comment',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u3',
      targetContentId: 'u3_v1',
      targetContentType: 'video',
      targetContentSummary: '这一镜头很有呼吸感',
      displaySubAccountId: 'u3',
      displayName: '城市观察者',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1680023410021-b7a2cbd7a1/v1/avatar.jpg',
      primaryText: '你评论了TA的记录：这一镜头很有呼吸感',
      previewMediaKind: 'video',
      previewImageUrl:
          'media/image/s/mock/seed/p_1646034296147-d8ed3aace9a4/v1/image.jpg',
      previewText: '城市夜行',
      filterKeys: const <String>['comments'],
      commentKind: 'comment',
      createdAt: '2025-12-21T09:40:00Z',
    ),
    _interactionWire(
      activityId: 'mock-sent-reply-$userId-u4',
      activityType: 'comment',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u4',
      targetContentId: 'u4_a1',
      targetContentType: 'comment',
      targetContentSummary: '谢谢你的推荐',
      displaySubAccountId: 'u4',
      displayName: '慢慢走',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1681123410021-f2d98a732e/v1/avatar.jpg',
      primaryText: '你回复了TA：谢谢你的推荐',
      contextText: 'TA说：可以试试傍晚再去',
      previewMediaKind: 'text',
      previewText: '城市散步路线',
      filterKeys: const <String>['comments'],
      commentKind: 'reply',
      createdAt: '2025-12-21T09:30:00Z',
    ),
    _interactionWire(
      activityId: 'mock-sent-share-$userId-u5',
      activityType: 'share',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u5',
      targetContentId: 'u5_a1',
      targetContentType: 'article',
      targetContentSummary: '适合周末出发的路线',
      displaySubAccountId: 'u5',
      displayName: '晴天存档',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1682223410021-d3ee771fe0/v1/avatar.jpg',
      primaryText: '你转发了TA的记录：适合下次出发前看',
      previewMediaKind: 'text',
      previewText: '适合周末出发的路线',
      filterKeys: const <String>['shares'],
      createdAt: '2025-12-21T09:20:00Z',
    ),
    _interactionWire(
      activityId: 'mock-sent-deleted-$userId-u6',
      activityType: 'like',
      direction: 'sent',
      actorSubAccountId: userId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      targetSubAccountId: 'u6',
      targetContentId: 'u6_gone',
      targetContentType: 'micro',
      targetContentSummary: '',
      displaySubAccountId: 'u6',
      displayName: '松间小路',
      displayAvatarUrl:
          'media/avatar/s/mock/seed/u_1683323410021-a07a1ef39e/v1/avatar.jpg',
      primaryText: '你点赞了TA的记录',
      previewMediaKind: 'none',
      previewUnavailable: true,
      filterKeys: const <String>['likes'],
      createdAt: '2025-12-21T09:10:00Z',
    ),
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
  final userHandle =
      profileRow?['userHandle']?.toString() ??
      profileRow?['username']?.toString() ??
      subAccountId;
  final username =
      profileRow?['username']?.toString() ??
      profileRow?['userHandle']?.toString() ??
      subAccountId;
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
      'viewerSubAccountId': ChatMockData.currentUserProfileId,
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

String _postSeedId(Map<String, dynamic> post) {
  return (post['postId'] ?? post['id'])?.toString() ?? '';
}

String _profileSeedName(
  Map<String, Map<String, dynamic>> profileById,
  String userId,
) {
  return profileById[userId]?['displayName']?.toString() ?? userId;
}

String _profileSeedAvatar(
  Map<String, Map<String, dynamic>> profileById,
  String userId,
) {
  return profileById[userId]?['avatarUrl']?.toString() ?? '';
}

int _profileSeedAvatarVersion(
  Map<String, Map<String, dynamic>> profileById,
  String userId,
) {
  return (profileById[userId]?['avatarVersion'] as num?)?.toInt() ?? 0;
}

String _postSeedContentType(Map<String, dynamic>? post) {
  return post?['contentType']?.toString() ?? post?['type']?.toString() ?? '';
}

String _postSeedSummary(Map<String, dynamic>? post) {
  if (post == null) {
    return '';
  }
  final title = post['title']?.toString() ?? '';
  if (title.trim().isNotEmpty) {
    return title;
  }
  final summary = post['summary']?.toString() ?? '';
  if (summary.trim().isNotEmpty) {
    return summary;
  }
  return post['body']?.toString() ?? '';
}

String _postSeedPreviewMediaKind(Map<String, dynamic>? post) {
  final contentType = _postSeedContentType(post);
  if (contentType == 'video') {
    return 'video';
  }
  if (contentType == 'image' || contentType == 'photo') {
    return 'image';
  }
  final image = _postSeedPreviewImageUrl(post);
  if (image.isNotEmpty && contentType != 'article' && contentType != 'micro') {
    return 'image';
  }
  return _postSeedSummary(post).isEmpty ? 'none' : 'text';
}

String _postSeedPreviewImageUrl(Map<String, dynamic>? post) {
  if (post == null) {
    return '';
  }
  final direct =
      post['coverUrl']?.toString() ?? post['thumbnailUrl']?.toString() ?? '';
  if (direct.trim().isNotEmpty) {
    return direct;
  }
  final mediaUrls = post['mediaUrls'];
  if (mediaUrls is List && mediaUrls.isNotEmpty) {
    return mediaUrls.first?.toString() ?? '';
  }
  return '';
}

String _commentSeedText(Map<String, dynamic> comment) {
  return comment['content']?.toString() ??
      comment['body']?.toString() ??
      comment['text']?.toString() ??
      '';
}

String _commentSeedKind(Map<String, dynamic> comment) {
  final parentCommentId = comment['parentCommentId']?.toString() ?? '';
  final replyToUserId = comment['replyToUserId']?.toString() ?? '';
  return parentCommentId.isNotEmpty || replyToUserId.isNotEmpty
      ? 'reply'
      : 'comment';
}

// 回复场景下的顶级评论 id，供互动深链在评论区高亮父评论行；
// 回退到 replyToCommentId（fixture 若未显式标注 parent）。
String _commentSeedParentId(Map<String, dynamic> comment) {
  final parentCommentId = comment['parentCommentId']?.toString() ?? '';
  if (parentCommentId.isNotEmpty) {
    return parentCommentId;
  }
  return comment['replyToCommentId']?.toString() ?? '';
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
          'likerAvatarVersion':
              (likerProfile?['avatarVersion'] as num?)?.toInt() ?? 0,
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
        final actorName = _profileSeedName(profileById, actorId);
        final actorAvatar = _profileSeedAvatar(profileById, actorId);
        return _interactionWire(
          activityId: 'like:$actorId:$postId',
          activityType: 'like',
          direction: 'received',
          actorSubAccountId: actorId,
          actorDisplayName: actorName,
          actorAvatarUrl: actorAvatar,
          actorAvatarVersion: _profileSeedAvatarVersion(profileById, actorId),
          targetSubAccountId: userId,
          targetContentId: postId,
          targetContentType: _postSeedContentType(post),
          targetContentSummary: _postSeedSummary(post),
          displaySubAccountId: actorId,
          displayName: actorName,
          displayAvatarUrl: actorAvatar,
          displayAvatarVersion: _profileSeedAvatarVersion(profileById, actorId),
          primaryText: '点赞了你的记录',
          previewMediaKind: _postSeedPreviewMediaKind(post),
          previewImageUrl: _postSeedPreviewImageUrl(post),
          previewText: _postSeedSummary(post),
          filterKeys: const <String>['likes'],
          createdAt: reaction['createdAt'] ?? reaction['updatedAt'],
        );
      })
      .whereType<Map<String, dynamic>>();
  final comments = _contentSeedComments().map((comment) {
    final postId = comment['postId']?.toString() ?? '';
    final actorId = comment['authorId']?.toString() ?? '';
    final post = postsById[postId];
    if (post == null || post['authorId']?.toString() != userId) {
      return null;
    }
    final commentText = _commentSeedText(comment);
    final commentKind = _commentSeedKind(comment);
    final actorName =
        comment['authorDisplayNameSnapshot']?.toString() ??
        _profileSeedName(profileById, actorId);
    final actorAvatar =
        comment['authorAvatarUrlSnapshot']?.toString() ??
        _profileSeedAvatar(profileById, actorId);
    return _interactionWire(
      activityId:
          comment['commentId']?.toString() ?? 'comment:$actorId:$postId',
      activityType: 'comment',
      direction: 'received',
      actorSubAccountId: actorId,
      actorDisplayName: actorName,
      actorAvatarUrl: actorAvatar,
      actorAvatarVersion: _profileSeedAvatarVersion(profileById, actorId),
      targetSubAccountId: userId,
      targetContentId: postId,
      targetContentType: _postSeedContentType(post),
      targetContentSummary: commentText,
      displaySubAccountId: actorId,
      displayName: actorName,
      displayAvatarUrl: actorAvatar,
      displayAvatarVersion: _profileSeedAvatarVersion(profileById, actorId),
      primaryText: commentKind == 'reply'
          ? '回复了你：$commentText'
          : '评论了你的记录：$commentText',
      contextText: commentKind == 'reply'
          ? comment['replyPreview']?.toString() ?? ''
          : '',
      previewMediaKind: _postSeedPreviewMediaKind(post),
      previewImageUrl: _postSeedPreviewImageUrl(post),
      previewText: _postSeedSummary(post),
      filterKeys: const <String>['comments'],
      commentKind: commentKind,
      commentId: comment['commentId']?.toString() ?? '',
      parentCommentId: _commentSeedParentId(comment),
      createdAt: comment['createdAt'],
    );
  }).whereType<Map<String, dynamic>>();
  return <Map<String, dynamic>>[...likes, ...comments];
}

List<Map<String, dynamic>> _contractInteractionSentWiresFor(String userId) {
  if (!_isContractFixtureUser(userId)) {
    return const <Map<String, dynamic>>[];
  }
  final postsById = <String, Map<String, dynamic>>{
    for (final post in _contentSeedPosts()) _postSeedId(post): post,
  };
  final profileById = <String, Map<String, dynamic>>{
    for (final row in _contractProfileRows()) row['userId'].toString(): row,
  };
  final likes = _contentSeedReactions()
      .where(
        (reaction) =>
            reaction['liked'] == true &&
            reaction['userId']?.toString() == userId,
      )
      .map((reaction) {
        final postId = reaction['postId']?.toString() ?? '';
        final post = postsById[postId];
        final targetUserId = post?['authorId']?.toString() ?? '';
        if (post == null || targetUserId.isEmpty || targetUserId == userId) {
          return null;
        }
        final actorName = _profileSeedName(profileById, userId);
        final actorAvatar = _profileSeedAvatar(profileById, userId);
        final displayName = _profileSeedName(profileById, targetUserId);
        return _interactionWire(
          activityId: 'like:$userId:$postId',
          activityType: 'like',
          direction: 'sent',
          actorSubAccountId: userId,
          actorDisplayName: actorName,
          actorAvatarUrl: actorAvatar,
          actorAvatarVersion: _profileSeedAvatarVersion(profileById, userId),
          targetSubAccountId: targetUserId,
          targetContentId: postId,
          targetContentType: _postSeedContentType(post),
          targetContentSummary: _postSeedSummary(post),
          displaySubAccountId: targetUserId,
          displayName: displayName,
          displayAvatarUrl: _profileSeedAvatar(profileById, targetUserId),
          displayAvatarVersion: _profileSeedAvatarVersion(
            profileById,
            targetUserId,
          ),
          primaryText: '你点赞了TA的记录',
          previewMediaKind: _postSeedPreviewMediaKind(post),
          previewImageUrl: _postSeedPreviewImageUrl(post),
          previewText: _postSeedSummary(post),
          filterKeys: const <String>['likes'],
          createdAt: reaction['createdAt'] ?? reaction['updatedAt'],
        );
      })
      .whereType<Map<String, dynamic>>();
  final comments = _contentSeedComments()
      .where((comment) => comment['authorId']?.toString() == userId)
      .map((comment) {
        final postId = comment['postId']?.toString() ?? '';
        final post = postsById[postId];
        final targetUserId = post?['authorId']?.toString() ?? '';
        if (post == null || targetUserId.isEmpty || targetUserId == userId) {
          return null;
        }
        final commentText = _commentSeedText(comment);
        final commentKind = _commentSeedKind(comment);
        final actorName =
            comment['authorDisplayNameSnapshot']?.toString() ??
            _profileSeedName(profileById, userId);
        final actorAvatar =
            comment['authorAvatarUrlSnapshot']?.toString() ??
            _profileSeedAvatar(profileById, userId);
        final displayName = _profileSeedName(profileById, targetUserId);
        return _interactionWire(
          activityId:
              comment['commentId']?.toString() ?? 'comment:$userId:$postId',
          activityType: 'comment',
          direction: 'sent',
          actorSubAccountId: userId,
          actorDisplayName: actorName,
          actorAvatarUrl: actorAvatar,
          actorAvatarVersion: _profileSeedAvatarVersion(profileById, userId),
          targetSubAccountId: targetUserId,
          targetContentId: postId,
          targetContentType: _postSeedContentType(post),
          targetContentSummary: commentText,
          displaySubAccountId: targetUserId,
          displayName: displayName,
          displayAvatarUrl: _profileSeedAvatar(profileById, targetUserId),
          displayAvatarVersion: _profileSeedAvatarVersion(
            profileById,
            targetUserId,
          ),
          primaryText: commentKind == 'reply'
              ? '你回复了TA：$commentText'
              : '你评论了TA的记录：$commentText',
          contextText: commentKind == 'reply'
              ? comment['replyPreview']?.toString() ?? ''
              : '',
          previewMediaKind: _postSeedPreviewMediaKind(post),
          previewImageUrl: _postSeedPreviewImageUrl(post),
          previewText: _postSeedSummary(post),
          filterKeys: const <String>['comments'],
          commentKind: commentKind,
          commentId: comment['commentId']?.toString() ?? '',
          parentCommentId: _commentSeedParentId(comment),
          createdAt: comment['createdAt'],
        );
      })
      .whereType<Map<String, dynamic>>();
  return <Map<String, dynamic>>[...likes, ...comments];
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
