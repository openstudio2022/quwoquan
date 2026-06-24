part of 'user_profile_repository.dart';

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
  Future<CursorPage<CircleDto>> listUserCirclesPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.userCirclesLimit,
  });
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    String? query,
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    final page = await listUserCirclesPage(userId, query: query, limit: limit);
    return page.items;
  }

  Future<UserProfileStatsViewData> getUserStats(String userId);

  /// 创作者影响力摘要（GetAuthorImpact，codegen DTO；displayText 云侧产出端只读直出）。
  Future<AuthorImpactSummary> getAuthorImpact(String userId);

  /// 创作者单条影响（impactId）的完整证据分页明细（ListAuthorImpactEvidence；R-ID03 端侧下钻闭合）。
  ///
  /// 端只读云侧分页结果（occurredAt 倒序，cursor opaque token，触底 hasMore=false），
  /// 以被影响内容为载体、不暴露产生影响的具体用户身份。alpha Mock 从同一
  /// `intersection_core` seed 对应的 [AuthorImpactItem] 派生分页明细，不新造第二套业务列表。
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String subAccountId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// 用户档案编辑 / 最近搜索维护。
///
/// R02：单接口 ≤10 方法。
abstract class ProfileEditRepository {
  Future<ProfileEditSnapshotData> getProfileEditSnapshot();

  Future<ProfileQrCardData> getProfileQrCard();

  /// 扫码落地解析（ResolveProfileQrToken）：校验公开主页 HTTPS payload 中的 opaque
  /// QR token，返回规范主页目标（subAccountId/userHandle/publicProfileUrl/scanStatus）。
  /// 端侧只透传 payload 中的 `qr`（token）与 `handle`，禁止自解析直跳到他人主页。
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  });

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
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowingPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<ProfileSocialRelationRowViewData>> listFollowing(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await listFollowingPage(
      userId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
    return page.items;
  }

  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowersPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<List<ProfileSocialRelationRowViewData>> listFollowers(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await listFollowersPage(
      userId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
    return page.items;
  }

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

  @override
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    String? query,
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    final page = await listUserCirclesPage(userId, query: query, limit: limit);
    return page.items;
  }

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowing(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await listFollowingPage(
      userId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
    return page.items;
  }

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowers(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await listFollowersPage(
      userId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
    return page.items;
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
