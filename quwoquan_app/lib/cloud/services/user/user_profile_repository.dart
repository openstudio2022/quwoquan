import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

/// 用户主页 Repository。
///
/// 接口方法与 contracts/metadata/user/user_profile/service.yaml、
/// contracts/metadata/user/follow_edge/service.yaml routes 一一对应。
abstract class UserProfileRepository {
  const UserProfileRepository();

  // ── 档案 ──────────────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> getUserProfile(String userId);
  Future<void> updateProfile(Map<String, dynamic> data);

  // ── 主页 Tab 数据 ─────────────────────────────────────────────────────────
  Future<List<PostBaseDto>> listUserPosts(
    String userId, {
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<UserWorkItem>> listUserWorks(String userId);
  Future<List<UserLifeItem>> listUserLifeItems(String userId);
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  });
  Future<Map<String, dynamic>> getUserStats(String userId);

  // ── 关注 / 粉丝 ──────────────────────────────────────────────────────────
  Future<void> followUser(String targetUserId);
  Future<void> unfollowUser(String targetUserId);
  Future<List<Map<String, dynamic>>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<Map<String, dynamic>>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<Map<String, dynamic>> getRelationship(String userId);
  Future<List<Map<String, dynamic>>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  // ── 互动（收到/发出）──────────────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<Map<String, dynamic>>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  // ── 分身 ──────────────────────────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> listPersonas();
  Future<Map<String, dynamic>> createPersona(Map<String, dynamic> data);
  Future<void> updatePersona(String personaId, Map<String, dynamic> data);
  Future<void> deletePersona(String personaId);
  Future<void> activatePersona(String personaId);

  Future<ProfileSubjectViewData> getProfileSubject(String userId) async {
    final profile = await getUserProfile(userId);
    final stats = await getUserStats(userId);
    return ProfileSubjectViewData.fromMap(profile).mergeStats(stats);
  }

  Future<List<ProfileCircleViewData>> listProfileCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    final items = await listUserCircles(userId, limit: limit);
    return items.map(ProfileCircleViewData.fromMap).toList(growable: false);
  }

  Future<List<ProfileInteractionActivityViewData>> listProfileInteractionReceivedView(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final items = await listUserInteractionReceived(
      userId,
      cursor: cursor,
      limit: limit,
    );
    return items
        .map(ProfileInteractionActivityViewData.fromMap)
        .toList(growable: false);
  }

  Future<List<ProfileInteractionActivityViewData>> listProfileInteractionSentView(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final items = await listUserInteractionSent(
      userId,
      cursor: cursor,
      limit: limit,
    );
    return items
        .map(ProfileInteractionActivityViewData.fromMap)
        .toList(growable: false);
  }
}

// ─── Mock 实现（本地数据，不发 HTTP）──────────────────────────────────────────

class MockUserProfileRepository extends UserProfileRepository {
  const MockUserProfileRepository();

  @override
  Future<Map<String, dynamic>> getUserProfile(String userId) async {
    return _mockProfiles[userId] ?? _defaultProfile(userId);
  }

  @override
  Future<void> updateProfile(Map<String, dynamic> data) async {}

  @override
  Future<List<PostBaseDto>> listUserPosts(
    String userId, {
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final posts = UserProfileMockData.userPostsFor(userId);
    return posts.take(limit).toList();
  }

  @override
  Future<List<UserWorkItem>> listUserWorks(String userId) async {
    return UserProfileMockData.worksFor(userId);
  }

  @override
  Future<List<UserLifeItem>> listUserLifeItems(String userId) async {
    return UserProfileMockData.lifeItemsFor(userId);
  }

  @override
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    return [
      {
        'id': 'c1',
        'name': '极简摄影俱乐部',
        'coverUrl':
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600',
        'memberCount': 2340,
        'postCount': 128,
      },
      {
        'id': 'c2',
        'name': '旅行手账',
        'coverUrl':
            'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600',
        'memberCount': 1280,
        'postCount': 56,
      },
      {
        'id': 'c3',
        'name': '咖啡品鉴',
        'coverUrl':
            'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
        'memberCount': 890,
        'postCount': 34,
      },
    ].take(limit).toList();
  }

  @override
  Future<Map<String, dynamic>> getUserStats(String userId) async {
    return {
      'followingCount': 284,
      'circleCount': 8,
      'followerCount': 1200,
      'likeCount': 4800,
    };
  }

  @override
  Future<void> followUser(String targetUserId) async {}

  @override
  Future<void> unfollowUser(String targetUserId) async {}

  @override
  Future<List<Map<String, dynamic>>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockRelationUsers.take(limit).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockRelationUsers.take(limit).toList();
  }

  @override
  Future<Map<String, dynamic>> getRelationship(String userId) async {
    return {'isFollowing': false, 'isFollowedBy': false, 'isMutual': false};
  }

  @override
  Future<List<Map<String, dynamic>>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockLikes.take(limit).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockInteractions.take(limit).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockInteractionsSent.take(limit).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listPersonas() async {
    return _mockPersonas;
  }

  @override
  Future<Map<String, dynamic>> createPersona(Map<String, dynamic> data) async {
    return {
      'id': 'new_persona_1',
      ...data,
      'isActive': false,
      'isPrimary': false,
    };
  }

  @override
  Future<void> updatePersona(
    String personaId,
    Map<String, dynamic> data,
  ) async {}

  @override
  Future<void> deletePersona(String personaId) async {}

  @override
  Future<void> activatePersona(String personaId) async {}

  // ── Mock 数据 ─────────────────────────────────────────────────────────────

  static Map<String, dynamic> _defaultProfile(String userId) {
    final chatName = ChatMockData.nameFor(userId);
    final hasChatIdentity = chatName != userId;
    return {
      'userId': userId,
      'nickname': hasChatIdentity ? chatName : userId,
      'avatarUrl': ChatMockData.avatarFor(userId),
      'bio': hasChatIdentity ? '趣屋圈用户' : '',
      'backgroundUrl':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200',
      'followerCount': hasChatIdentity ? 120 : 0,
      'followingCount': hasChatIdentity ? 85 : 0,
      'postCount': hasChatIdentity ? 30 : 0,
      'circleCount': hasChatIdentity ? 3 : 0,
      'likeCount': hasChatIdentity ? 480 : 0,
    };
  }

  static final Map<String, Map<String, dynamic>> _mockProfiles = {
    'user_001': {
      'userId': 'user_001',
      'nickname': '趣我圈用户',
      'avatarUrl': ChatMockData.avatarFor('user_001'),
      'bio': '关心时事、关注新闻、思考人生、思索生命',
      'backgroundUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'followerCount': 120,
      'followingCount': 85,
      'postCount': 30,
      'circleCount': 3,
      'likeCount': 480,
    },
    'nature_photographer': {
      'userId': 'nature_photographer',
      'nickname': '自然摄影师',
      'avatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'bio': '用镜头记录自然之美',
      'backgroundUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'followerCount': 1200,
      'followingCount': 284,
      'postCount': 156,
      'circleCount': 8,
      'likeCount': 4800,
    },
    'travel_photographer': {
      'userId': 'travel_photographer',
      'nickname': '旅行摄影师',
      'avatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'bio': '在路上，遇见世界',
      'backgroundUrl':
          'https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200',
      'followerCount': 890,
      'followingCount': 156,
      'postCount': 89,
      'circleCount': 5,
      'likeCount': 3200,
    },
    'a1': {
      'userId': 'a1',
      'nickname': '楹语小筑',
      'avatarUrl':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
      'bio': '分享美好生活',
      'backgroundUrl':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200',
      'followerCount': 2400,
      'followingCount': 320,
      'postCount': 230,
      'circleCount': 12,
      'likeCount': 9600,
    },
  };

  static final List<Map<String, dynamic>> _mockRelationUsers = [
    {
      'userId': 'u1',
      'nickname': '你的皮炎有点辣',
      'avatarUrl':
          'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      'bio': '美食探索者',
      'isFollowing': true,
    },
    {
      'userId': 'u2',
      'nickname': '仅分组可见',
      'avatarUrl':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
      'bio': '设计师',
      'isFollowing': false,
    },
    {
      'userId': 'u3',
      'nickname': '原价帝吧',
      'avatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'bio': '数码爱好者',
      'isFollowing': true,
    },
    {
      'userId': 'u4',
      'nickname': '李想',
      'avatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'bio': '产品经理',
      'isFollowing': false,
    },
  ];

  static final List<Map<String, dynamic>> _mockInteractions = [
    {
      'userId': 'u1',
      'nickname': '你的皮炎有点辣',
      'avatarUrl':
          'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      'activityType': 'like',
      'contentType': 'like',
      'targetTitle': '赞了你的《川西秘境摄影集》',
      'createdAt': '2025-12-21T10:00:00Z',
    },
    {
      'userId': 'u2',
      'nickname': '王小明',
      'avatarUrl':
          'https://images.unsplash.com/photo-1643816831234-e7cb32194e92?w=100',
      'activityType': 'comment',
      'contentType': 'comment',
      'targetTitle': '评论了你的《摄影器材交流区》',
      'createdAt': '2025-12-20T10:05:00Z',
    },
    {
      'userId': 'u3',
      'nickname': '原价帝吧',
      'avatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'activityType': 'share',
      'contentType': 'share',
      'targetTitle': '转发了你的《森林的呼吸》',
      'createdAt': '2025-12-20T08:00:00Z',
    },
    {
      'userId': 'u4',
      'nickname': '李想',
      'avatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'activityType': 'like',
      'contentType': 'like',
      'targetTitle': '赞了你的《光影的节奏》',
      'createdAt': '2025-12-19T16:00:00Z',
    },
  ];

  static final List<Map<String, dynamic>> _mockInteractionsSent = [
    {
      'userId': 'u3',
      'nickname': '原价帝吧',
      'avatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'activityType': 'comment',
      'contentType': 'comment',
      'targetTitle': '你评论了《森林的呼吸》',
      'createdAt': '2025-12-19T14:00:00Z',
    },
    {
      'userId': 'u1',
      'nickname': '你的皮炎有点辣',
      'avatarUrl':
          'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      'activityType': 'share',
      'contentType': 'share',
      'targetTitle': '你转发了《川西秘境摄影集》',
      'createdAt': '2025-12-18T20:00:00Z',
    },
    {
      'userId': 'u4',
      'nickname': '李想',
      'avatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'activityType': 'like',
      'contentType': 'like',
      'targetTitle': '你赞了《光影的节奏》',
      'createdAt': '2025-12-17T18:30:00Z',
    },
  ];

  static final List<Map<String, dynamic>> _mockLikes = [
    {
      'postId': 'p1',
      'title': '光影的节奏',
      'coverUrl':
          'https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=400',
      'likerNickname': '你的皮炎有点辣',
      'likerAvatarUrl':
          'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      'likedAt': '2025-12-21T10:00:00Z',
    },
    {
      'postId': 'p2',
      'title': '森林的呼吸',
      'coverUrl':
          'https://images.unsplash.com/photo-1646034296147-d8ed3aace9a4?q=80&w=400',
      'likerNickname': '原价帝吧',
      'likerAvatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'likedAt': '2025-12-20T15:00:00Z',
    },
  ];

  static final List<Map<String, dynamic>> _mockPersonas = [
    {
      'id': 'persona_primary',
      'displayName': '主身份',
      'avatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'isPrimary': true,
      'isPrivate': false,
      'isActive': true,
    },
    {
      'id': 'persona_anon',
      'displayName': '匿名身份',
      'avatarUrl':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100',
      'isPrimary': false,
      'isPrivate': true,
      'isActive': false,
    },
  ];
}

// ─── Remote 实现（调用云侧 API）───────────────────────────────────────────────

class RemoteUserProfileRepository extends UserProfileRepository {
  RemoteUserProfileRepository({http.Client? client})
    : _client = client ?? http.Client();

  final http.Client _client;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '${CloudRuntimeConfig.gatewayBaseUrl}$path',
    ).replace(queryParameters: queryParameters);
  }

  List<Map<String, dynamic>> _decodeItems(http.Response resp) {
    final data = json.decode(resp.body) as Map<String, dynamic>;
    return (data['items'] as List? ?? <dynamic>[]).cast<Map<String, dynamic>>();
  }

  static String _normalizeRelationshipState(Map<String, dynamic> map) {
    final state =
        map['relationState']?.toString() ??
        map['relationTier']?.toString() ??
        '';
    if (state.isNotEmpty) {
      switch (state) {
        case 'same_interest':
        case 'close_friend':
          return 'mutual';
        case 'following_only':
          return 'following';
        case 'none':
          return 'not_following';
      }
      return state;
    }
    final isFollowing = map['isFollowing'] == true;
    final isFollowedBy = map['isFollowedBy'] == true;
    if (isFollowing && isFollowedBy) return 'mutual';
    if (isFollowing) return 'following';
    if (isFollowedBy) return 'followed_by';
    return 'not_following';
  }

  static Map<String, dynamic> _normalizeRelationshipItem(Map<String, dynamic> raw) {
    final profileSubjectId =
        raw['profileSubjectId']?.toString() ??
        raw['targetProfileSubjectId']?.toString() ??
        raw['userId']?.toString() ??
        '';
    final displayName =
        raw['displayName']?.toString() ??
        raw['nickname']?.toString() ??
        profileSubjectId;
    final avatarUrl =
        raw['avatarUrl']?.toString() ??
        raw['avatarUrlSnapshot']?.toString() ??
        '';
    return <String, dynamic>{
      ...raw,
      'profileSubjectId': profileSubjectId,
      'userId': profileSubjectId,
      'displayName': displayName,
      'nickname': displayName,
      'avatarUrl': avatarUrl,
    };
  }

  static Map<String, dynamic> _normalizeRelationship(Map<String, dynamic> raw) {
    final relationState = _normalizeRelationshipState(raw);
    final isMutual = relationState == 'mutual';
    final isFollowing = relationState == 'following' || isMutual;
    final isFollowedBy = relationState == 'followed_by' || isMutual;
    return <String, dynamic>{
      ..._normalizeRelationshipItem(raw),
      'relationState': relationState,
      'isFollowing': raw['isFollowing'] == true || isFollowing,
      'isFollowedBy': raw['isFollowedBy'] == true || isFollowedBy,
      'isMutual': raw['isMutual'] == true || isMutual,
    };
  }

  // ── 档案 ──────────────────────────────────────────────────────────────────

  @override
  Future<Map<String, dynamic>> getUserProfile(String userId) async {
    if (userId == 'me') {
      final meUrl = _uri(UserApiMetadata.getMeProfilePath);
      final meResp = await _client.get(
        meUrl,
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.getMeProfile),
      );
      if (meResp.statusCode == 200) {
        return json.decode(meResp.body) as Map<String, dynamic>;
      }
    }

    final subjectUrl = _uri(
      UserApiMetadata.getSubAccountProfilePath(subAccountId: userId),
    );
    final subjectResp = await _client.get(
      subjectUrl,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getSubAccountProfile,
      ),
    );
    if (subjectResp.statusCode == 200) {
      return json.decode(subjectResp.body) as Map<String, dynamic>;
    }

    final legacyUrl = _uri(UserApiMetadata.getUserProfilePath(userId: userId));
    final legacyResp = await _client.get(
      legacyUrl,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getUserProfile),
    );
    if (legacyResp.statusCode != 200) {
      throw Exception(
        'getUserProfile failed: subject=${subjectResp.statusCode}, legacy=${legacyResp.statusCode}',
      );
    }
    return json.decode(legacyResp.body) as Map<String, dynamic>;
  }

  @override
  Future<void> updateProfile(Map<String, dynamic> data) async {
    final url = _uri(UserApiMetadata.updateUserProfilePath);
    final resp = await _client.patch(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updateUserProfile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    if (resp.statusCode != 200) {
      throw Exception('updateProfile failed: ${resp.statusCode}');
    }
  }

  // ── 主页 Tab 数据 ─────────────────────────────────────────────────────────

  @override
  Future<List<PostBaseDto>> listUserPosts(
    String userId, {
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final url = _uri(
      ContentApiMetadata.listUserPostsPath(profileSubjectId: userId),
      queryParameters: <String, String>{'limit': '$limit'},
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listUserPosts),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserPosts failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = (data['items'] as List? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return items.map(postBaseDtoFromMap).toList();
  }

  @override
  Future<List<UserWorkItem>> listUserWorks(String userId) async {
    final url = _uri(UserApiMetadata.listUserWorksPath(userId: userId));
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listUserWorks),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserWorks failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = (data['items'] as List? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return items.map(_workItemFromMap).toList();
  }

  @override
  Future<List<UserLifeItem>> listUserLifeItems(String userId) async {
    final url = _uri(UserApiMetadata.listUserLifeItemsPath(userId: userId));
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listUserLifeItems,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserLifeItems failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = (data['items'] as List? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return items.map(_lifeItemFromMap).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    final url = _uri(
      CircleApiMetadata.listUserCirclesPath(userId: userId),
      queryParameters: <String, String>{'limit': '$limit'},
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listUserCircles,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserCircles failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    return (data['items'] as List? ?? <dynamic>[]).cast<Map<String, dynamic>>();
  }

  @override
  Future<Map<String, dynamic>> getUserStats(String userId) async {
    final profile = await getUserProfile(userId);
    return {
      'followingCount': profile['followingCount'] ?? 0,
      'circleCount': profile['circleCount'] ?? 0,
      'followerCount': profile['followerCount'] ?? 0,
      'likeCount': profile['likeCount'] ?? 0,
    };
  }

  // ── 关注 / 粉丝 ──────────────────────────────────────────────────────────

  @override
  Future<void> followUser(String targetUserId) async {
    final url = _uri(
      UserApiMetadata.followUserPath(
        targetProfileSubjectId: targetUserId,
      ),
    );
    final resp = await _client.post(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.followUser),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('followUser failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> unfollowUser(String targetUserId) async {
    final url = _uri(
      UserApiMetadata.unfollowUserPath(
        targetProfileSubjectId: targetUserId,
      ),
    );
    final resp = await _client.delete(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.unfollowUser),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('unfollowUser failed: ${resp.statusCode}');
    }
  }

  @override
  Future<List<Map<String, dynamic>>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      UserApiMetadata.listFollowingPath(profileSubjectId: userId),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listFollowing),
    );
    if (resp.statusCode != 200) {
      throw Exception('listFollowing failed: ${resp.statusCode}');
    }
    return _decodeItems(resp)
        .map(_normalizeRelationshipItem)
        .toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      UserApiMetadata.listFollowersPath(profileSubjectId: userId),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listFollowers),
    );
    if (resp.statusCode != 200) {
      throw Exception('listFollowers failed: ${resp.statusCode}');
    }
    return _decodeItems(resp)
        .map(_normalizeRelationshipItem)
        .toList(growable: false);
  }

  @override
  Future<Map<String, dynamic>> getRelationship(String userId) async {
    final url = _uri(
      UserApiMetadata.getRelationshipPath(profileSubjectId: userId),
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getRelationship),
    );
    if (resp.statusCode != 200) {
      throw Exception('getRelationship failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    return _normalizeRelationship(data);
  }

  @override
  Future<List<Map<String, dynamic>>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      UserApiMetadata.listUserLikesPath(userId: userId),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listUserLikes),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserLikes failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    return (data['items'] as List? ?? <dynamic>[]).cast<Map<String, dynamic>>();
  }

  @override
  Future<List<Map<String, dynamic>>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      ContentApiMetadata.listProfileInteractionActivitiesReceivedPath(
        profileSubjectId: userId,
      ),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listProfileInteractionActivitiesReceived,
      ),
    );
    if (resp.statusCode == 200) {
      return _decodeItems(resp);
    }
    if (resp.statusCode == 204 || resp.statusCode == 404 || resp.statusCode == 501) {
      return <Map<String, dynamic>>[];
    }
    throw Exception('listUserInteractionReceived failed: ${resp.statusCode}');
  }

  @override
  Future<List<Map<String, dynamic>>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      ContentApiMetadata.listProfileInteractionActivitiesSentPath(
        profileSubjectId: userId,
      ),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listProfileInteractionActivitiesSent,
      ),
    );
    if (resp.statusCode == 200) {
      return _decodeItems(resp);
    }
    if (resp.statusCode == 204 || resp.statusCode == 404 || resp.statusCode == 501) {
      return <Map<String, dynamic>>[];
    }
    throw Exception('listUserInteractionSent failed: ${resp.statusCode}');
  }

  // ── 分身 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listPersonas() async {
    final url = _uri(UserApiMetadata.listPersonasPath);
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listPersonas),
    );
    if (resp.statusCode != 200) {
      throw Exception('listPersonas failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    return (data['items'] as List? ?? <dynamic>[]).cast<Map<String, dynamic>>();
  }

  @override
  Future<Map<String, dynamic>> createPersona(Map<String, dynamic> data) async {
    final url = _uri(UserApiMetadata.createPersonaPath);
    final resp = await _client.post(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.createPersona),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('createPersona failed: ${resp.statusCode}');
    }
    return json.decode(resp.body) as Map<String, dynamic>;
  }

  @override
  Future<void> updatePersona(
    String personaId,
    Map<String, dynamic> data,
  ) async {
    final url = _uri(UserApiMetadata.updatePersonaPath(personaId: personaId));
    final resp = await _client.patch(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updatePersona),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    if (resp.statusCode != 200) {
      throw Exception('updatePersona failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> deletePersona(String personaId) async {
    final url = _uri(UserApiMetadata.deletePersonaPath(personaId: personaId));
    final resp = await _client.delete(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.deletePersona),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('deletePersona failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> activatePersona(String personaId) async {
    final url = _uri(UserApiMetadata.activatePersonaPath(personaId: personaId));
    final resp = await _client.post(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activatePersona),
    );
    if (resp.statusCode != 200) {
      throw Exception('activatePersona failed: ${resp.statusCode}');
    }
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  static UserWorkItem _workItemFromMap(Map<String, dynamic> m) {
    return UserWorkItem(
      id: m['id']?.toString() ?? '',
      type: m['type']?.toString() ?? '',
      title: m['title']?.toString() ?? '',
      coverUrl: m['coverUrl']?.toString() ?? '',
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      date: m['date']?.toString() ?? '',
      desc: m['desc']?.toString() ?? '',
    );
  }

  static UserLifeItem _lifeItemFromMap(Map<String, dynamic> m) {
    return UserLifeItem(
      id: m['id']?.toString() ?? '',
      name: m['name']?.toString() ?? '',
      category: m['category']?.toString() ?? '',
      categoryKey: m['categoryKey']?.toString() ?? '',
      coverUrl: m['coverUrl']?.toString() ?? '',
      desc: m['desc']?.toString() ?? '',
    );
  }
}
