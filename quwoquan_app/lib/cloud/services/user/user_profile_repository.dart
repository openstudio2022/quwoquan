import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_bundle_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_user_like_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_normalized_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

part 'user_profile_contract_seed_helpers.dart';
part 'user_profile_repository_remote.dart';

PersonaDto _personaDtoFromWire(Map<String, dynamic> json) {
  final m = Map<String, dynamic>.from(json);
  m.putIfAbsent('id', () => '');
  m.putIfAbsent('userId', () => '');
  m.putIfAbsent('displayName', () => '');
  m.putIfAbsent('createdAt', () => '');
  m.putIfAbsent('updatedAt', () => '');
  return PersonaDto.fromJson(m);
}

List<ProfileInteractionActivityViewData> _interactionViewDataListFromWires(
  Iterable<Map<String, dynamic>> wires, {
  required int limit,
}) {
  final items = wires
      .map(
        (m) =>
            ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
              ProfileInteractionActivityWireDto.fromMap(m),
            ),
      )
      .toList(growable: false);
  final sorted = [...items]
    ..sort((a, b) {
      final aTime = a.createdAt;
      final bTime = b.createdAt;
      if (aTime == null && bTime == null) {
        return a.activityId.compareTo(b.activityId);
      }
      if (aTime == null) return 1;
      if (bTime == null) return -1;
      return bTime.compareTo(aTime);
    });
  return sorted.take(limit).toList(growable: false);
}

/// JSON 编码前去掉 null，避免 PATCH 误传「显式 null」覆盖服务端字段。
Map<String, dynamic> _omitNullMapValues(Map<String, dynamic> source) {
  return Map<String, dynamic>.fromEntries(
    source.entries.where((e) => e.value != null),
  );
}

/// 用户档案读取 / 主页 Tab 数据 / 统计 / 关系检索。
///
/// R02：单接口 ≤10 方法。
abstract class ProfileReadRepository {
  // ── 档案 ──────────────────────────────────────────────────────────────────
  Future<SubAccountProfileViewData> getUserProfile(String userId);

  /// 主页首屏聚合（GetUserHomepageBundle，锁定决策 #1）：一次返回 profile / stats /
  /// relationshipCapability / tabCounts / viewerContext / cacheVersion，消除首屏串行
  /// 阻塞。交集卡与影响力 evidence 属 content 域，由端侧并发补充，不进 bundle。
  Future<UserHomepageBundleViewData> getUserHomepageBundle(String subAccountId);

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

  /// 创作者影响力摘要（GetAuthorImpact，codegen DTO；displayText 云侧产出端只读直出）。
  Future<AuthorImpactSummary> getAuthorImpact(String userId);

  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// 用户档案编辑 / 最近搜索维护。
///
/// R02：单接口 ≤10 方法。
abstract class ProfileEditRepository {
  Future<void> updateProfile(ProfileEditUpdatePayload data);

  Future<List<RecentSearchEntryView>> listRecentSearches();

  Future<RecentSearchEntryView> upsertRecentSearch({
    required String query,
    required SearchScope scope,
    String? facet,
  });

  Future<void> deleteRecentSearch(String entryId);

  Future<void> clearRecentSearches();
}

/// 用户关注 / 粉丝 / 关系 / 点赞 / 互动。
///
/// R02：单接口 ≤10 方法。
abstract class ProfileRelationshipRepository {
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
}

/// 用户分身（persona）管理。
///
/// R02：单接口 ≤10 方法。
abstract class ProfilePersonaRepository {
  // ── 分身 ──────────────────────────────────────────────────────────────────
  Future<List<PersonaDto>> listPersonas();
  Future<PersonaDto> createPersona(PersonaCreateRequestDto request);
  Future<void> updatePersona(
    String subAccountId,
    PersonaUpdateRequestDto request,
  );
  Future<void> deletePersona(String subAccountId);
  Future<void> activatePersona(String subAccountId);
}

/// 用户主页 Repository。
///
/// 接口方法与 contracts/metadata/user/user_profile/service.yaml、
/// contracts/metadata/user/follow_edge/service.yaml routes 一一对应。
///
/// 由 4 个 ≤10 方法子接口组合（R02）。既有消费方继续依赖 `UserProfileRepository`
/// 不变；新消费方可只依赖所需子接口。下方的便捷默认方法由子类（Mock / Remote）
/// 经 `extends` 继承。
abstract class UserProfileRepository
    implements
        ProfileReadRepository,
        ProfileEditRepository,
        ProfileRelationshipRepository,
        ProfilePersonaRepository {
  const UserProfileRepository();

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
}

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
    final wire = SubAccountProfileWireDto.fromMap(_defaultProfile(userId));
    return SubAccountProfileViewData.fromSubAccountProfileWire(wire);
  }

  /// Mock 本人态判定（开发态约定）：'me' / contract 当前用户 / 默认用户视为本人。
  static const Set<String> _ownerLikeSubAccountIds = <String>{
    'me',
    'fixture_user_current',
    'user_001',
  };

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    final profile = await getUserProfile(subAccountId);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    final isOwner = _ownerLikeSubAccountIds.contains(subAccountId);
    final relation = await getRelationship(subAccountId);
    final viewerSubAccountId = isOwner ? subAccountId : 'fixture_user_current';
    final relationshipCapability = isOwner
        ? null
        : RelationshipCapabilityDto.fromFollowFlags(
            viewerId: viewerSubAccountId,
            targetId: subAccountId,
            isFollowing: relation.isFollowing,
            isFollowedBy: relation.isFollowedBy,
            hasFormalConversation: relation.isMutual,
          );
    return UserHomepageBundleViewData(
      profile: profile,
      stats: stats,
      relationshipCapability: relationshipCapability,
      tabCounts: UserHomepageTabCountsViewData.fromStats(stats),
      viewerContext: UserHomepageViewerContextViewData(
        viewerSubAccountId: viewerSubAccountId,
        isOwner: isOwner,
        isGuest: false,
        relationToTarget: isOwner ? 'self' : relation.relationState,
        canViewFullProfile: true,
      ),
      cacheVersion:
          'mock-${profile.subAccountId}-${profile.updatedAt?.toIso8601String() ?? 'static'}',
    );
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
            'media/image/s/mock/seed/p_1506905925346-21bda4d32df4/v1/image.jpg',
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
            'media/image/s/mock/seed/p_1501785888041-af3ef285b470/v1/image.jpg',
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
            'media/image/s/mock/seed/p_1495474472287-4d71bcdd2085/v1/image.jpg',
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
  Future<AuthorImpactSummary> getAuthorImpact(String userId) async {
    // Contract seed（intersection_core.authorImpact）驱动；无 seed/未登记作者时返回空摘要（不造假）。
    final seed = ContractFixtureRuntimeLoader.contentSeedSet(
      'intersection_core',
    );
    final impactByAuthor = seed?['authorImpact'];
    if (impactByAuthor is Map) {
      final entry = impactByAuthor[userId];
      if (entry is Map) {
        return AuthorImpactSummary.fromMap(entry.cast<String, dynamic>());
      }
    }
    return AuthorImpactSummary(authorId: userId);
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
    return _contractProfileRows()
        .where((user) {
          final displayName = (user['displayName'] ?? '').toString();
          final headline = (user['bio'] ?? '').toString();
          return displayName.toLowerCase().contains(normalizedQuery) ||
              headline.toLowerCase().contains(normalizedQuery);
        })
        .take(limit)
        .map((user) {
          final subAccountId = user['userId']?.toString() ?? '';
          final relationship =
              _contractRelationshipByTargetUserId[subAccountId];
          final relationState =
              relationship?['relationState']?.toString() ?? 'not_following';
          final isFollowing = relationship?['isFollowing'] == true;
          final hasFormalConversation =
              relationState == 'mutual' || isFollowing;
          final wire = SocialRelationSearchItemWireDto(
            subAccountId: subAccountId,
            username: subAccountId,
            displayName: (user['displayName'] ?? subAccountId).toString(),
            avatarUrl: user['avatarUrl']?.toString(),
            headline: (user['bio'] ?? '').toString(),
            chatAvailable: true,
            relationshipCapability: <String, dynamic>{
              'relationState': relationState,
              'canFollow': !isFollowing,
              'canUnfollow': isFollowing,
              'hasFormalConversation': hasFormalConversation,
              'canOpenConversation': hasFormalConversation,
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
    final contractRows = _contractFollowingWiresFor(userId);
    if (contractRows.isNotEmpty) {
      return contractRows
          .take(limit)
          .map(
            (m) =>
                ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                  ProfileSocialRelationRowWireDto.fromMap(m),
                ),
          )
          .toList(growable: false);
    }
    return _mockFollowingWiresFor(userId)
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
    final contractRows = _contractFollowerWiresFor(userId);
    if (contractRows.isNotEmpty) {
      return contractRows
          .take(limit)
          .map(
            (m) =>
                ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                  ProfileSocialRelationRowWireDto.fromMap(m),
                ),
          )
          .toList(growable: false);
    }
    return _mockFollowerWiresFor(userId)
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
    return RelationshipViewData.fromRelationshipNormalizedWire(
      RelationshipNormalizedWireDto(
        relationState: 'not_following',
        isFollowing: false,
        isFollowedBy: false,
        isMutual: false,
      ),
    );
  }

  @override
  Future<List<ProfileUserLikeRowViewData>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractLikes = _contractLikeWiresFor(userId);
    if (contractLikes.isNotEmpty) {
      return contractLikes
          .take(limit)
          .map(
            (m) => ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
              ProfileUserLikeRowWireDto.fromMap(m),
            ),
          )
          .toList(growable: false);
    }
    return const <ProfileUserLikeRowViewData>[];
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractItems = _contractInteractionReceivedWiresFor(userId);
    if (contractItems.isNotEmpty) {
      return _interactionViewDataListFromWires(contractItems, limit: limit);
    }
    return _interactionViewDataListFromWires(
      _mockInteractionReceivedWiresFor(userId),
      limit: limit,
    );
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractItems = _contractInteractionSentWiresFor(userId);
    if (contractItems.isNotEmpty) {
      return _interactionViewDataListFromWires(contractItems, limit: limit);
    }
    return _interactionViewDataListFromWires(
      _mockInteractionSentWiresFor(userId),
      limit: limit,
    );
  }

  @override
  Future<List<PersonaDto>> listPersonas() async {
    final contractPersonas = _contractPersonaRows();
    if (contractPersonas.isNotEmpty) {
      return contractPersonas.map(_personaDtoFromWire).toList(growable: false);
    }
    return const <PersonaDto>[];
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
}

// ─── Remote 实现（调用云侧 API）───────────────────────────────────────────────

