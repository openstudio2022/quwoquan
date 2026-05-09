import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_user_like_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_normalized_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/ui/user/models/resonance_buddy_view_data.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

PersonaDto _personaDtoFromWire(Map<String, dynamic> json) {
  final m = Map<String, dynamic>.from(json);
  m.putIfAbsent('id', () => '');
  m.putIfAbsent('userId', () => '');
  m.putIfAbsent('displayName', () => '');
  m.putIfAbsent('createdAt', () => '');
  m.putIfAbsent('updatedAt', () => '');
  return PersonaDto.fromJson(m);
}

/// JSON 编码前去掉 null，避免 PATCH 误传「显式 null」覆盖服务端字段。
Map<String, dynamic> _omitNullMapValues(Map<String, dynamic> source) {
  return Map<String, dynamic>.fromEntries(
    source.entries.where((e) => e.value != null),
  );
}

/// 用户主页 Repository。
///
/// 接口方法与 contracts/metadata/user/user_profile/service.yaml、
/// contracts/metadata/user/follow_edge/service.yaml routes 一一对应。
abstract class UserProfileRepository {
  const UserProfileRepository();

  // ── 档案 ──────────────────────────────────────────────────────────────────
  Future<SubAccountProfileViewData> getUserProfile(String userId);
  Future<void> updateProfile(ProfileEditUpdatePayload data);

  // ── 主页 Tab 数据 ─────────────────────────────────────────────────────────
  Future<List<PostBaseDto>> listUserPosts(
    String userId, {
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<UserWorkItem>> listUserWorks(String userId);
  Future<List<UserLifeItem>> listUserLifeItems(String userId);
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  });
  Future<UserProfileStatsViewData> getUserStats(String userId);

  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<RecentSearchEntryView>> listRecentSearches();

  Future<RecentSearchEntryView> upsertRecentSearch({
    required String query,
    required SearchScope scope,
    String? facet,
  });

  Future<void> deleteRecentSearch(String entryId);

  Future<void> clearRecentSearches();

  // ── 关注 / 粉丝 ──────────────────────────────────────────────────────────
  Future<void> followUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  });
  Future<void> unfollowUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  });
  Future<List<ProfileSocialRelationRowViewData>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<ProfileSocialRelationRowViewData>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<RelationshipViewData> getRelationship(String userId);
  Future<List<ProfileUserLikeRowViewData>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  // ── 互动（收到/发出）──────────────────────────────────────────────────────
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  // ── 分身 ──────────────────────────────────────────────────────────────────
  Future<List<PersonaDto>> listPersonas();
  Future<PersonaDto> createPersona(PersonaCreateRequestDto request);
  Future<void> updatePersona(
    String subAccountId,
    PersonaUpdateRequestDto request,
  );
  Future<void> deletePersona(String subAccountId);
  Future<void> activatePersona(String subAccountId);

  Future<SubAccountProfileViewData> getSubAccountProfile(String userId) async {
    final profile = await getUserProfile(userId);
    final stats = await getUserStats(userId);
    return profile.mergeStats(stats);
  }

  Future<List<CircleDto>> listProfileCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    return listUserCircles(userId, limit: limit);
  }

  Future<List<ProfileInteractionActivityViewData>>
  listProfileInteractionReceivedView(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return listUserInteractionReceived(userId, cursor: cursor, limit: limit);
  }

  Future<List<ProfileInteractionActivityViewData>>
  listProfileInteractionSentView(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return listUserInteractionSent(userId, cursor: cursor, limit: limit);
  }

  /// 「我的交集」内嵌预览行；云侧未接 API 时为 empty。
  List<Map<String, dynamic>> resonanceBuddyPreviewWireRows();
}

/// 预置用户档案 JSON：`jsonDecode` 后与远程 `getUserProfile` 同形进入 [SubAccountProfileWireDto]。
const String _kBundledMockUserProfilesJson = r'''
{
  "user_001": {
    "userId": "user_001",
    "nickname": "趣我圈用户",
    "avatarUrl": "https://i.pravatar.cc/150?u=user_001",
    "bio": "关心时事、关注新闻、思考人生、思索生命",
    "backgroundUrl": "https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200",
    "followerCount": 120,
    "followingCount": 85,
    "postCount": 30,
    "circleCount": 3,
    "likeCount": 480
  },
  "nature_photographer": {
    "userId": "nature_photographer",
    "nickname": "自然摄影师",
    "avatarUrl": "https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100",
    "bio": "用镜头记录自然之美",
    "backgroundUrl": "https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200",
    "followerCount": 1200,
    "followingCount": 284,
    "postCount": 156,
    "circleCount": 8,
    "likeCount": 4800
  },
  "travel_photographer": {
    "userId": "travel_photographer",
    "nickname": "旅行摄影师",
    "avatarUrl": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100",
    "bio": "在路上，遇见世界",
    "backgroundUrl": "https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200",
    "followerCount": 890,
    "followingCount": 156,
    "postCount": 89,
    "circleCount": 5,
    "likeCount": 3200
  },
  "a1": {
    "userId": "a1",
    "nickname": "楹语小筑",
    "avatarUrl": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100",
    "bio": "分享美好生活",
    "backgroundUrl": "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200",
    "followerCount": 2400,
    "followingCount": 320,
    "postCount": 230,
    "circleCount": 12,
    "likeCount": 9600
  }
}
''';

Map<String, Map<String, dynamic>> _decodeBundledMockUserProfiles(String raw) {
  final root = CloudResponseDecoder.asObject(
    json.decode(raw),
    context: UserRequestPageIds.getUserProfile,
  );
  return root.map(
    (k, v) => MapEntry(
      k,
      CloudResponseDecoder.asObject(
        v,
        context: UserRequestPageIds.getUserProfile,
      ),
    ),
  );
}

List<Map<String, dynamic>> _decodeJsonObjectList(String raw) {
  final decoded = json.decode(raw);
  if (decoded is! List) {
    return const <Map<String, dynamic>>[];
  }
  return decoded
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);
}

const String _kMockRelationUsersJson = r'''
[
  {"userId":"u1","nickname":"你的皮炎有点辣","avatarUrl":"https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100","bio":"美食探索者","isFollowing":true},
  {"userId":"u2","nickname":"仅分组可见","avatarUrl":"https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100","bio":"设计师","isFollowing":false},
  {"userId":"u3","nickname":"原价帝吧","avatarUrl":"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100","bio":"数码爱好者","isFollowing":true},
  {"userId":"u4","nickname":"李想","avatarUrl":"https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100","bio":"产品经理","isFollowing":false}
]
''';

const String _kMockInteractionsJson = r'''
[
  {"userId":"u1","nickname":"你的皮炎有点辣","avatarUrl":"https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100","activityType":"like","contentType":"like","targetTitle":"赞了你的《川西秘境摄影集》","createdAt":"2025-12-21T10:00:00Z"},
  {"userId":"u2","nickname":"王小明","avatarUrl":"https://images.unsplash.com/photo-1643816831234-e7cb32194e92?w=100","activityType":"comment","contentType":"comment","targetTitle":"评论了你的《摄影器材交流区》","createdAt":"2025-12-20T10:05:00Z"},
  {"userId":"u3","nickname":"原价帝吧","avatarUrl":"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100","activityType":"share","contentType":"share","targetTitle":"转发了你的《森林的呼吸》","createdAt":"2025-12-20T08:00:00Z"},
  {"userId":"u4","nickname":"李想","avatarUrl":"https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100","activityType":"like","contentType":"like","targetTitle":"赞了你的《光影的节奏》","createdAt":"2025-12-19T16:00:00Z"}
]
''';

const String _kMockInteractionsSentJson = r'''
[
  {"userId":"u3","nickname":"原价帝吧","avatarUrl":"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100","activityType":"comment","contentType":"comment","targetTitle":"你评论了《森林的呼吸》","createdAt":"2025-12-19T14:00:00Z"},
  {"userId":"u1","nickname":"你的皮炎有点辣","avatarUrl":"https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100","activityType":"share","contentType":"share","targetTitle":"你转发了《川西秘境摄影集》","createdAt":"2025-12-18T20:00:00Z"},
  {"userId":"u4","nickname":"李想","avatarUrl":"https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100","activityType":"like","contentType":"like","targetTitle":"你赞了《光影的节奏》","createdAt":"2025-12-17T18:30:00Z"}
]
''';

const String _kMockLikesJson = r'''
[
  {"postId":"p1","title":"光影的节奏","coverUrl":"https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=400","likerNickname":"你的皮炎有点辣","likerAvatarUrl":"https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100","likedAt":"2025-12-21T10:00:00Z"},
  {"postId":"p2","title":"森林的呼吸","coverUrl":"https://images.unsplash.com/photo-1646034296147-d8ed3aace9a4?q=80&w=400","likerNickname":"原价帝吧","likerAvatarUrl":"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100","likedAt":"2025-12-20T15:00:00Z"}
]
''';

// ─── Mock 实现（本地数据，不发 HTTP）──────────────────────────────────────────

class MockUserProfileRepository extends UserProfileRepository {
  const MockUserProfileRepository();

  static final List<RecentSearchEntryWireDto> _recentSearchEntries =
      <RecentSearchEntryWireDto>[];

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    final contractWire = _contractProfileWireByUserId[userId];
    if (contractWire != null) {
      return SubAccountProfileViewData.fromSubAccountProfileWire(contractWire);
    }
    final wire =
        _mockProfileWireByUserId[userId] ??
        SubAccountProfileWireDto.fromMap(_defaultProfile(userId));
    return SubAccountProfileViewData.fromSubAccountProfileWire(wire);
  }

  @override
  Future<void> updateProfile(ProfileEditUpdatePayload data) async {}

  @override
  Future<List<PostBaseDto>> listUserPosts(
    String userId, {
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractPosts = _contractPostsForUser(userId);
    if (contractPosts.isNotEmpty) {
      return contractPosts.take(limit).toList(growable: false);
    }
    final posts = UserProfileMockData.userPostsFor(userId);
    return posts.take(limit).toList();
  }

  @override
  Future<List<UserWorkItem>> listUserWorks(String userId) async {
    final contractPosts = _contractPostsForUser(userId);
    if (contractPosts.isNotEmpty) {
      return contractPosts
          .map(_contractWorkItemFromPost)
          .toList(growable: false);
    }
    return UserProfileMockData.worksFor(userId);
  }

  @override
  Future<List<UserLifeItem>> listUserLifeItems(String userId) async {
    return UserProfileMockData.lifeItemsFor(userId);
  }

  @override
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    final contractCircles = _contractProfileWireByUserId.containsKey(userId)
        ? _contractUserCircles()
        : const <CircleDto>[];
    if (contractCircles.isNotEmpty) {
      return contractCircles.take(limit).toList(growable: false);
    }
    final t = DateTime.parse('2025-01-01T00:00:00Z');
    final circles = <CircleDto>[
      CircleDto(
        id: 'c1',
        name: '极简摄影俱乐部',
        coverUrl:
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600',
        ownerId: userId,
        memberCount: 2340,
        postCount: 128,
        createdAt: t,
        updatedAt: t,
      ),
      CircleDto(
        id: 'c2',
        name: '旅行手账',
        coverUrl:
            'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600',
        ownerId: userId,
        memberCount: 1280,
        postCount: 56,
        createdAt: t,
        updatedAt: t,
      ),
      CircleDto(
        id: 'c3',
        name: '咖啡品鉴',
        coverUrl:
            'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
        ownerId: userId,
        memberCount: 890,
        postCount: 34,
        createdAt: t,
        updatedAt: t,
      ),
    ];
    return circles.take(limit).toList(growable: false);
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    final profile = await getUserProfile(userId);
    return UserProfileStatsViewData.fromProfile(profile);
  }

  @override
  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <SocialRelationSearchItemView>[];
    }
    return _mockRelationUsers
        .where((user) {
          final displayName = (user['displayName'] ?? user['nickname'] ?? '')
              .toString();
          final headline = (user['headline'] ?? user['bio'] ?? '').toString();
          return displayName.toLowerCase().contains(normalizedQuery) ||
              headline.toLowerCase().contains(normalizedQuery);
        })
        .take(limit)
        .map((user) {
          final subAccountId =
              user['subAccountId']?.toString() ??
              user['userId']?.toString() ??
              '';
          final relationState = UserProfileMockData.relationStateValueFor(
            subAccountId,
          );
          final isFollowing = UserProfileMockData.viewerFollowsTarget(
            subAccountId,
          );
          final wire = SocialRelationSearchItemWireDto(
            subAccountId: subAccountId,
            username: (user['username'] ?? user['nickname'] ?? '').toString(),
            displayName: (user['displayName'] ?? user['nickname'] ?? '')
                .toString(),
            avatarUrl: user['avatarUrl']?.toString(),
            headline: (user['headline'] ?? user['bio'] ?? '').toString(),
            chatAvailable: true,
            relationshipCapability: <String, dynamic>{
              'relationState': relationState,
              'canFollow': !isFollowing,
              'canUnfollow': isFollowing,
              'canOpenConversation': relationState == 'mutual',
            },
          );
          return SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
            wire,
            wire.toMap(),
          );
        })
        .toList(growable: false);
  }

  @override
  Future<List<RecentSearchEntryView>> listRecentSearches() async {
    return _recentSearchEntries
        .map(RecentSearchEntryView.fromRecentSearchEntryWire)
        .toList(growable: false);
  }

  @override
  Future<RecentSearchEntryView> upsertRecentSearch({
    required String query,
    required SearchScope scope,
    String? facet,
  }) async {
    final scopeValue = scope.wireValue;
    final seed = '$scopeValue|${facet ?? ''}|${query.trim().toLowerCase()}';
    final entryId = 'recent_${seed.hashCode.abs().toRadixString(16)}';
    _recentSearchEntries.removeWhere((entry) => entry.entryId == entryId);
    final entry = RecentSearchEntryWireDto(
      entryId: entryId,
      query: query,
      scope: scopeValue,
      facet: facet,
      updatedAt: DateTime.now(),
    );
    _recentSearchEntries.insert(0, entry);
    return RecentSearchEntryView.fromRecentSearchEntryWire(entry);
  }

  @override
  Future<void> deleteRecentSearch(String entryId) async {
    _recentSearchEntries.removeWhere((entry) => entry.entryId == entryId);
  }

  @override
  Future<void> clearRecentSearches() async {
    _recentSearchEntries.clear();
  }

  @override
  Future<void> followUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {}

  @override
  Future<void> unfollowUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {}

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockRelationUsers
        .where(
          (user) => UserProfileMockData.viewerFollowsTarget(
            _subAccountIdOf(user),
          ),
        )
        .map(_withMockRelationship)
        .take(limit)
        .map(
          (m) =>
              ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                ProfileSocialRelationRowWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockRelationUsers
        .where(
          (user) => UserProfileMockData.targetFollowsViewer(
            _subAccountIdOf(user),
          ),
        )
        .map(_withMockRelationship)
        .take(limit)
        .map(
          (m) =>
              ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                ProfileSocialRelationRowWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<RelationshipViewData> getRelationship(String userId) async {
    final contractRelationship = _contractRelationshipByTargetUserId[userId];
    if (contractRelationship != null) {
      return RelationshipViewData.fromRelationshipNormalizedWire(
        RelationshipNormalizedWireDto.fromMap(contractRelationship),
      );
    }
    final relationState = UserProfileMockData.relationStateValueFor(userId);
    final isFollowing = UserProfileMockData.viewerFollowsTarget(userId);
    final isFollowedBy = UserProfileMockData.targetFollowsViewer(userId);
    return RelationshipViewData.fromRelationshipNormalizedWire(
      RelationshipNormalizedWireDto(
        relationState: relationState,
        isFollowing: isFollowing,
        isFollowedBy: isFollowedBy,
        isMutual: relationState == 'mutual',
      ),
    );
  }

  @override
  Future<List<ProfileUserLikeRowViewData>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockLikes
        .take(limit)
        .map(
          (m) => ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
            ProfileUserLikeRowWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockInteractions
        .take(limit)
        .map(
          (m) =>
              ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
                ProfileInteractionActivityWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _mockInteractionsSent
        .take(limit)
        .map(
          (m) =>
              ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
                ProfileInteractionActivityWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<PersonaDto>> listPersonas() async {
    return _mockPersonas.map(_personaDtoFromWire).toList(growable: false);
  }

  @override
  Future<PersonaDto> createPersona(PersonaCreateRequestDto request) async {
    final wire = _omitNullMapValues(request.toMap());
    final isolation = request.isolationLevel;
    final isPrivate = isolation == 'strict';
    return _personaDtoFromWire(<String, dynamic>{
      'id': 'new_persona_1',
      ...wire,
      'isActive': false,
      'isPrimary': false,
      'isPrivate': isPrivate,
    });
  }

  @override
  Future<void> updatePersona(
    String subAccountId,
    PersonaUpdateRequestDto request,
  ) async {}

  @override
  Future<void> deletePersona(String subAccountId) async {}

  @override
  Future<void> activatePersona(String subAccountId) async {}

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

  static List<Map<String, dynamic>> _contractProfileRows() {
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

  static List<Map<String, dynamic>> _contractRelationshipRows() {
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

  static List<PostBaseDto> _contractPostsForUser(String userId) {
    if (!_contractProfileWireByUserId.containsKey(userId)) {
      return const <PostBaseDto>[];
    }
    final feedSeed = ContractFixtureRuntimeLoader.userSeedSet(
      'profile_feed_core',
    );
    final contentSeed = ContractFixtureRuntimeLoader.contentSeedSet();
    final posts = contentSeed?['posts'];
    if (posts is! List) {
      return const <PostBaseDto>[];
    }
    final selectedIds = feedSeed == null
        ? null
        : userId == 'fixture_user_current'
        ? feedSeed['myPostIds']
        : feedSeed['authorPostIds'];
    final ids = selectedIds is List
        ? selectedIds.map((id) => id.toString()).toSet()
        : const <String>{};
    if (ids.isEmpty) {
      return const <PostBaseDto>[];
    }
    return posts
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .where((item) => ids.contains(item['id'] ?? item['postId']))
        .map(postBaseDtoFromMap)
        .toList(growable: false);
  }

  static UserWorkItem _contractWorkItemFromPost(PostBaseDto post) {
    return UserWorkItem(
      id: post.id,
      type: post.type,
      title: post.normalizedTitle.isNotEmpty
          ? post.normalizedTitle
          : post.normalizedBody,
      coverUrl: post.primaryVisualUrl,
      likeCount: post.likeCount,
      date: post.createdAt.toIso8601String(),
      desc: post.normalizedBody,
    );
  }

  static List<CircleDto> _contractUserCircles() {
    final seed = ContractFixtureRuntimeLoader.circleSeedSet();
    final circles = seed?['circles'];
    if (circles is! List) {
      return const <CircleDto>[];
    }
    return circles
        .whereType<Map>()
        .map((item) => CircleDto.fromMap(item.cast<String, dynamic>()))
        .toList(growable: false);
  }

  static Map<String, dynamic> _contractProfileWire(Map<String, dynamic> item) {
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

  static final Map<String, SubAccountProfileWireDto> _mockProfileWireByUserId = {
    for (final e in _decodeBundledMockUserProfiles(
      _kBundledMockUserProfilesJson,
    ).entries)
      e.key: SubAccountProfileWireDto.fromMap(e.value),
  };

  static final Map<String, SubAccountProfileWireDto> _contractProfileWireByUserId =
      {
        for (final item in _contractProfileRows())
          item['userId'].toString(): SubAccountProfileWireDto.fromMap(
            _contractProfileWire(item),
          ),
      };

  static final Map<String, Map<String, dynamic>>
  _contractRelationshipByTargetUserId = {
    for (final item in _contractRelationshipRows())
      item['targetUserId'].toString(): <String, dynamic>{
        'relationState': item['mutualFollow'] == true
            ? 'mutual'
            : item['following'] == true
            ? 'following'
            : 'none',
        'isFollowing': item['following'] == true,
        'isFollowedBy': item['mutualFollow'] == true,
        'isMutual': item['mutualFollow'] == true,
      },
  };

  static final List<Map<String, dynamic>> _mockRelationUsers =
      _decodeJsonObjectList(_kMockRelationUsersJson);

  static final List<Map<String, dynamic>> _mockInteractions =
      _decodeJsonObjectList(_kMockInteractionsJson);

  static final List<Map<String, dynamic>> _mockInteractionsSent =
      _decodeJsonObjectList(_kMockInteractionsSentJson);

  static final List<Map<String, dynamic>> _mockLikes = _decodeJsonObjectList(
    _kMockLikesJson,
  );

  /// Wire 键与 [PersonaDto] / user_profile `ListPersonas` 响应字段对齐（见 contracts/metadata/user/user_profile）。
  static final List<Map<String, dynamic>> _mockPersonas = [
    {
      'id': 'persona_primary',
      'userId': 'user_persona_primary',
      'displayName': '主身份',
      'avatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'isPrimary': true,
      'isPrivate': false,
      'isActive': true,
      'createdAt': '2025-01-01T00:00:00Z',
      'updatedAt': '2025-01-01T00:00:00Z',
    },
    {
      'id': 'persona_anon',
      'userId': 'user_persona_anon',
      'displayName': '匿名身份',
      'avatarUrl':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100',
      'isPrimary': false,
      'isPrivate': true,
      'isActive': false,
      'createdAt': '2025-01-01T00:00:00Z',
      'updatedAt': '2025-01-01T00:00:00Z',
    },
  ];

  static String _subAccountIdOf(Map<String, dynamic> user) {
    return user['subAccountId']?.toString() ??
        user['userId']?.toString() ??
        '';
  }

  static Map<String, dynamic> _withMockRelationship(Map<String, dynamic> user) {
    final subAccountId = _subAccountIdOf(user);
    final relationState = UserProfileMockData.relationStateValueFor(
      subAccountId,
    );
    return <String, dynamic>{
      ...user,
      'subAccountId': subAccountId,
      'relationState': relationState,
      'isFollowing': UserProfileMockData.viewerFollowsTarget(subAccountId),
      'isFollowedBy': UserProfileMockData.targetFollowsViewer(subAccountId),
      'isMutual': relationState == 'mutual',
    };
  }

  @override
  List<Map<String, dynamic>> resonanceBuddyPreviewWireRows() {
    return ResonanceBuddyViewData.prototype
        .map((e) => e.toWireMap())
        .toList(growable: false);
  }
}

// ─── Remote 实现（调用云侧 API）───────────────────────────────────────────────

class RemoteUserProfileRepository extends UserProfileRepository {
  RemoteUserProfileRepository({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  List<Map<String, dynamic>> _decodeItems(http.Response resp, String context) {
    final decoded = json.decode(resp.body);
    final obj = CloudResponseDecoder.asObject(decoded, context: context);
    return CloudResponseDecoder.mapList(obj, 'items');
  }

  List<T> _decodeItemsAs<T>(
    http.Response resp,
    String context,
    T Function(Map<String, dynamic> m) map,
  ) {
    return _decodeItems(resp, context).map(map).toList(growable: false);
  }

  Map<String, dynamic> _decodeObject(http.Response resp, String context) {
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: context,
    );
    final payload = data['data'];
    if (payload is Map<String, dynamic>) {
      return payload;
    }
    if (payload is Map) {
      return Map<String, dynamic>.from(payload);
    }
    return data;
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

  static Map<String, dynamic> _normalizeRelationshipItem(
    Map<String, dynamic> raw,
  ) {
    final subAccountId =
        raw['subAccountId']?.toString() ??
        raw['targetSubAccountId']?.toString() ??
        raw['userId']?.toString() ??
        '';
    final displayName =
        raw['displayName']?.toString() ??
        raw['nickname']?.toString() ??
        subAccountId;
    final avatarUrl =
        raw['avatarUrl']?.toString() ??
        raw['avatarUrlSnapshot']?.toString() ??
        '';
    return <String, dynamic>{
      ...raw,
      'subAccountId': subAccountId,
      'userId': subAccountId,
      'displayName': displayName,
      'nickname': displayName,
      'avatarUrl': avatarUrl,
    };
  }

  static RelationshipNormalizedWireDto relationshipNormalizedFromRaw(
    Map<String, dynamic> raw,
  ) {
    final relationState = _normalizeRelationshipState(raw);
    final isMutual = relationState == 'mutual';
    final isFollowing = relationState == 'following' || isMutual;
    final isFollowedBy = relationState == 'followed_by' || isMutual;
    return RelationshipNormalizedWireDto(
      relationState: relationState,
      isFollowing: raw['isFollowing'] == true || isFollowing,
      isFollowedBy: raw['isFollowedBy'] == true || isFollowedBy,
      isMutual: raw['isMutual'] == true || isMutual,
    );
  }

  // ── 档案 ──────────────────────────────────────────────────────────────────

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    if (userId == 'me') {
      final meUrl = _uri(UserApiMetadata.getMeProfilePath);
      final meResp = await _client.get(
        meUrl,
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.getMeProfile),
      );
      if (meResp.statusCode == 200) {
        final map = CloudResponseDecoder.asObject(
          json.decode(meResp.body),
          context: UserRequestPageIds.getMeProfile,
        );
        return SubAccountProfileViewData.fromSubAccountProfileWire(
          SubAccountProfileWireDto.fromMap(map),
        );
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
      final map = CloudResponseDecoder.asObject(
        json.decode(subjectResp.body),
        context: UserRequestPageIds.getSubAccountProfile,
      );
      return SubAccountProfileViewData.fromSubAccountProfileWire(
        SubAccountProfileWireDto.fromMap(map),
      );
    }

    throw Exception('getUserProfile failed: subject=${subjectResp.statusCode}');
  }

  @override
  Future<void> updateProfile(ProfileEditUpdatePayload data) async {
    final url = _uri(UserApiMetadata.updateUserProfilePath);
    final resp = await _client.patch(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updateUserProfile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toRepositoryMap()),
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
      ContentApiMetadata.listUserPostsPath(subAccountId: userId),
      queryParameters: <String, String>{'limit': '$limit'},
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listUserPosts),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserPosts failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: ContentRequestPageIds.listUserPosts,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
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
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listUserWorks,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
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
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listUserLifeItems,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(_lifeItemFromMap).toList();
  }

  @override
  Future<List<CircleDto>> listUserCircles(
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
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: CircleRequestPageIds.listUserCircles,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(CircleDto.fromMap).toList(growable: false);
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    final profile = await getUserProfile(userId);
    return UserProfileStatsViewData.fromProfile(profile);
  }

  @override
  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final url = _uri(
      UserApiMetadata.searchSocialRelationsPath,
      queryParameters: <String, String>{'query': query, 'limit': '$limit'},
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.searchSocialRelations,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('searchSocialRelations failed: ${resp.statusCode}');
    }
    return _decodeItemsAs(resp, UserRequestPageIds.searchSocialRelations, (m) {
      final w = SocialRelationSearchItemWireDto.fromMap(m);
      return SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
        w,
        m,
      );
    });
  }

  @override
  Future<List<RecentSearchEntryView>> listRecentSearches() async {
    final url = _uri(UserApiMetadata.listRecentSearchesPath);
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listRecentSearches,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listRecentSearches failed: ${resp.statusCode}');
    }
    return _decodeItemsAs(
      resp,
      UserRequestPageIds.listRecentSearches,
      (m) => RecentSearchEntryView.fromRecentSearchEntryWire(
        RecentSearchEntryWireDto.fromMap(m),
      ),
    );
  }

  @override
  Future<RecentSearchEntryView> upsertRecentSearch({
    required String query,
    required SearchScope scope,
    String? facet,
  }) async {
    final scopeValue = scope.wireValue;
    final seed = '$scopeValue|${facet ?? ''}|${query.trim().toLowerCase()}';
    final entryId = 'recent_${seed.hashCode.abs().toRadixString(16)}';
    final url = _uri(UserApiMetadata.upsertRecentSearchPath(entryId: entryId));
    final resp = await _client.put(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.upsertRecentSearch),
        'Content-Type': 'application/json',
      },
      body: json.encode(<String, dynamic>{
        'query': query,
        'scope': scopeValue,
        'facet': facet,
        'updatedAt': DateTime.now().toIso8601String(),
      }),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('upsertRecentSearch failed: ${resp.statusCode}');
    }
    return RecentSearchEntryView.fromRecentSearchEntryWire(
      RecentSearchEntryWireDto.fromMap(
        _decodeObject(resp, UserRequestPageIds.upsertRecentSearch),
      ),
    );
  }

  @override
  Future<void> deleteRecentSearch(String entryId) async {
    final url = _uri(UserApiMetadata.deleteRecentSearchPath(entryId: entryId));
    final resp = await _client.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteRecentSearch,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('deleteRecentSearch failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> clearRecentSearches() async {
    final url = _uri(UserApiMetadata.clearRecentSearchesPath);
    final resp = await _client.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.clearRecentSearches,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('clearRecentSearches failed: ${resp.statusCode}');
    }
  }

  // ── 关注 / 粉丝 ──────────────────────────────────────────────────────────

  @override
  Future<void> followUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    final url = _uri(
      UserApiMetadata.followUserPath(targetSubAccountId: targetUserId),
    );
    final resp = await _client.post(
      url,
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(UserRequestPageIds.followUser),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('followUser failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> unfollowUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    final url = _uri(
      UserApiMetadata.unfollowUserPath(targetSubAccountId: targetUserId),
    );
    final resp = await _client.delete(
      url,
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(UserRequestPageIds.unfollowUser),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('unfollowUser failed: ${resp.statusCode}');
    }
  }

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      UserApiMetadata.listFollowingPath(subAccountId: userId),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listFollowing),
    );
    if (resp.statusCode != 200) {
      throw Exception('listFollowing failed: ${resp.statusCode}');
    }
    return _decodeItems(resp, UserRequestPageIds.listFollowing)
        .map(_normalizeRelationshipItem)
        .map(
          (m) =>
              ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                ProfileSocialRelationRowWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      UserApiMetadata.listFollowersPath(subAccountId: userId),
      queryParameters: params,
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listFollowers),
    );
    if (resp.statusCode != 200) {
      throw Exception('listFollowers failed: ${resp.statusCode}');
    }
    return _decodeItems(resp, UserRequestPageIds.listFollowers)
        .map(_normalizeRelationshipItem)
        .map(
          (m) =>
              ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                ProfileSocialRelationRowWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<RelationshipViewData> getRelationship(String userId) async {
    final url = _uri(
      UserApiMetadata.getRelationshipPath(subAccountId: userId),
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getRelationship),
    );
    if (resp.statusCode != 200) {
      throw Exception('getRelationship failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.getRelationship,
    );
    return RelationshipViewData.fromRelationshipNormalizedWire(
      relationshipNormalizedFromRaw(data),
    );
  }

  @override
  Future<List<ProfileUserLikeRowViewData>> listUserLikes(
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
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listUserLikes,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items
        .map(
          (m) => ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
            ProfileUserLikeRowWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      ContentApiMetadata.listProfileInteractionActivitiesReceivedPath(
        subAccountId: userId,
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
      return _decodeItemsAs(
        resp,
        ContentRequestPageIds.listProfileInteractionActivitiesReceived,
        (m) =>
            ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
              ProfileInteractionActivityWireDto.fromMap(m),
            ),
      );
    }
    if (resp.statusCode == 204 ||
        resp.statusCode == 404 ||
        resp.statusCode == 501) {
      return const <ProfileInteractionActivityViewData>[];
    }
    throw Exception('listUserInteractionReceived failed: ${resp.statusCode}');
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      ContentApiMetadata.listProfileInteractionActivitiesSentPath(
        subAccountId: userId,
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
      return _decodeItemsAs(
        resp,
        ContentRequestPageIds.listProfileInteractionActivitiesSent,
        (m) =>
            ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
              ProfileInteractionActivityWireDto.fromMap(m),
            ),
      );
    }
    if (resp.statusCode == 204 ||
        resp.statusCode == 404 ||
        resp.statusCode == 501) {
      return const <ProfileInteractionActivityViewData>[];
    }
    throw Exception('listUserInteractionSent failed: ${resp.statusCode}');
  }

  // ── 分身 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<PersonaDto>> listPersonas() async {
    final url = _uri(UserApiMetadata.listPersonasPath);
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listPersonas),
    );
    if (resp.statusCode != 200) {
      throw Exception('listPersonas failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listPersonas,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(_personaDtoFromWire).toList(growable: false);
  }

  @override
  Future<PersonaDto> createPersona(PersonaCreateRequestDto request) async {
    final url = _uri(UserApiMetadata.createPersonaPath);
    final bodyMap = _omitNullMapValues(request.toMap());
    final resp = await _client.post(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.createPersona),
        'Content-Type': 'application/json',
      },
      body: json.encode(bodyMap),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('createPersona failed: ${resp.statusCode}');
    }
    final body = json.decode(resp.body);
    final map = CloudResponseDecoder.asObject(
      body,
      context: UserRequestPageIds.createPersona,
    );
    return _personaDtoFromWire(map);
  }

  @override
  Future<void> updatePersona(
    String subAccountId,
    PersonaUpdateRequestDto request,
  ) async {
    final url = _uri(
      UserApiMetadata.updatePersonaPath(subAccountId: subAccountId),
    );
    final bodyMap = _omitNullMapValues(request.toMap());
    final resp = await _client.patch(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updatePersona),
        'Content-Type': 'application/json',
      },
      body: json.encode(bodyMap),
    );
    if (resp.statusCode != 200) {
      throw Exception('updatePersona failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> deletePersona(String subAccountId) async {
    final url = _uri(
      UserApiMetadata.deleteEmptyPersonaPath(subAccountId: subAccountId),
    );
    final resp = await _client.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteEmptyPersona,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('deletePersona failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> activatePersona(String subAccountId) async {
    final url = _uri(
      UserApiMetadata.activatePersonaPath(subAccountId: subAccountId),
    );
    final resp = await _client.post(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activatePersona),
    );
    if (resp.statusCode != 200) {
      throw Exception('activatePersona failed: ${resp.statusCode}');
    }
  }

  @override
  List<Map<String, dynamic>> resonanceBuddyPreviewWireRows() => const [];

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
