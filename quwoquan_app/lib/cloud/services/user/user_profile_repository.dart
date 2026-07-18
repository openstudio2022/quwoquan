import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_edit_snapshot_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_card_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_bundle_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_user_like_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_normalized_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/runtime/prefab_user_resolver.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:quwoquan_app/core/auth/mock_session_identity.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

part 'user_profile_contract_seed_helpers.dart';
part 'user_profile_contract_seed_helpers_interactions.dart';
part 'user_profile_repository_helpers.dart';
part 'user_profile_repository_contract.dart';
part 'user_profile_repository_relationship_normalization.dart';
part 'user_profile_repository_remote.dart';

typedef _ProfileEditSnapshotOverrideMap =
    Map<String, ProfileEditSnapshotWireDto>;

// ─── Mock 实现（本地数据，不发 HTTP）──────────────────────────────────────────

class MockUserProfileRepository extends UserProfileRepository {
  const MockUserProfileRepository();

  static final List<RecentSearchEntryWireDto> _recentSearchEntries =
      <RecentSearchEntryWireDto>[];

  /// 本人在 mock 下保存的资料覆盖（开发态进程内持久化）。
  ///
  /// key = subAccountId；value = 合并后的完整 wire。保存成功后 [getUserProfile]
  /// 立即读到同一真相源，保证「我的主页」即时回显新昵称 / 简介 / 头像 / 封面，
  /// 不再是空实现导致的「保存后无变化」。
  static final Map<String, SubAccountProfileWireDto> _profileOverrides =
      <String, SubAccountProfileWireDto>{};

  /// 本人编辑页私有快照覆盖。
  ///
  /// 公开主页 wire 不承载生日、性别、地区等私有编辑字段；这些字段必须在
  /// ProfileEditSnapshotWire 维度独立往返，避免编辑页再次进入时退回空值。
  static final _ProfileEditSnapshotOverrideMap _profileEditSnapshotOverrides =
      _ProfileEditSnapshotOverrideMap();

  /// 解析某个用户的基础 wire（覆盖优先，其次契约种子，最后默认档案）。
  SubAccountProfileWireDto _baseProfileWire(String userId) {
    final override = _profileOverrides[userId];
    if (override != null) {
      return _normalizeCurrentUserVariantWire(userId, override);
    }
    if (_ownerLikeSubAccountIds.contains(userId)) {
      final currentOverride = _profileOverrides[kMockCurrentSubAccountId];
      if (currentOverride != null) {
        return _normalizeCurrentUserVariantWire(userId, currentOverride);
      }
    }
    return _normalizeCurrentUserVariantWire(
      userId,
      resolveMockUserProfileWire(userId),
    );
  }

  SubAccountProfileWireDto _normalizeCurrentUserVariantWire(
    String requestedId,
    SubAccountProfileWireDto wire,
  ) {
    if (!_ownerLikeSubAccountIds.contains(requestedId)) {
      return wire;
    }
    return wire.copyWith(
      ownerUserId: kMockCurrentOwnerId,
      subAccountId: kMockCurrentSubAccountId,
    );
  }

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    return SubAccountProfileViewData.fromSubAccountProfileWire(
      _baseProfileWire(userId),
    );
  }

  /// Mock 本人态判定（开发态约定）：'me' 或 contract 当前用户视为本人。
  static Set<String> get _ownerLikeSubAccountIds => {
    'me',
    'fixture_user_current',
    'user_001',
    PrefabUserResolver.currentUserVariantSubAccountId,
    PrefabUserResolver.currentUserVariantUserId,
  };

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    final resolvedId = PrefabUserResolver.resolveSubAccountId(subAccountId);
    final profile = await getUserProfile(resolvedId);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    final isOwner =
        _ownerLikeSubAccountIds.contains(subAccountId) ||
        _ownerLikeSubAccountIds.contains(resolvedId);
    final relation = await getRelationship(resolvedId);
    final viewerSubAccountId = isOwner
        ? resolvedId
        : PrefabUserResolver.currentUserVariantSubAccountId;
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
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    final profile = await getUserProfile(kMockCurrentSubAccountId);
    final credentials = await listCredentialsForProfileEdit();
    final base = ProfileEditSnapshotData.fromProfile(
      profile: profile,
      credentials: credentials,
    );
    final override = _resolveMockProfileEditSnapshotWire(
      kMockCurrentSubAccountId,
    );
    if (override == null) {
      return base;
    }
    return base.copyWithPrivateFieldsFromWire(override);
  }

  Future<List<OwnerCredentialRowDto>> listCredentialsForProfileEdit() async {
    return <OwnerCredentialRowDto>[
      OwnerCredentialRowDto.fromMap(<String, dynamic>{
        'id': 'mock_cred_1',
        'credentialType': 'phone',
        'displayLabel': '138****0001',
        'isActive': true,
        'boundAt': DateTime.now().toIso8601String(),
      }),
    ];
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    final snapshot = await getProfileEditSnapshot();
    return snapshot.qrCard ?? ProfileQrCardData.mockFromSnapshot(snapshot);
  }

  @override
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    final normalizedToken = token.trim();
    if (normalizedToken.isEmpty) {
      throw Exception('resolveProfileQrToken: empty qr token');
    }
    final normalizedHandle = handle.trim().toLowerCase();
    final rows = _contractProfileRows();
    Map<String, dynamic>? hit;
    if (normalizedHandle.isNotEmpty) {
      for (final row in rows) {
        if ((row['userId'] ?? '').toString().toLowerCase() ==
            normalizedHandle) {
          hit = row;
          break;
        }
      }
    }
    hit ??= rows.isNotEmpty ? rows.first : null;
    final subAccountId = hit?['userId']?.toString() ?? normalizedHandle;
    return ProfileQrResolveWireDto(
      subAccountId: subAccountId,
      userHandle: subAccountId,
      publicProfileUrl: 'https://app.quwoquan.com/u/$subAccountId',
      scanStatus: 'accepted',
    );
  }

  @override
  Future<void> updateProfile(ProfileEditUpdatePayload data) async {
    if (data.isEmpty) {
      return;
    }
    // mock 资料编辑恒为「编辑本人资料」，落到 canonical 当前用户上（与登录态
    // currentUserIdProvider 同源）。按 PATCH 语义只改本次携带的字段。
    final subAccountId = kMockCurrentSubAccountId;
    var next = _baseProfileWire(subAccountId);
    var editNext =
        _resolveMockProfileEditSnapshotWire(subAccountId) ??
        _profileEditSnapshotWireFromProfile(next);
    final nickname = data.nickname;
    if (nickname != null) {
      // 昵称同时回填 displayName，并标记 nicknameCustomized=true（主页画笔随之隐藏）。
      next = next.copyWith(
        nickname: nickname,
        displayName: nickname,
        nicknameCustomized: true,
      );
      editNext = editNext.copyWith(nickname: nickname, displayName: nickname);
    }
    final bio = data.bio;
    if (bio != null) {
      next = next.copyWith(bio: bio);
      editNext = editNext.copyWith(bio: bio);
    }
    final avatarUrl = data.avatarUrl;
    if (avatarUrl != null) {
      next = next.copyWith(avatarUrl: avatarUrl);
      editNext = editNext.copyWith(
        avatarUrl: avatarUrl,
        avatarAssetId: data.avatarAssetId,
      );
    }
    final backgroundUrl = data.backgroundUrl;
    if (backgroundUrl != null) {
      next = next.copyWith(backgroundUrl: backgroundUrl);
      editNext = editNext.copyWith(
        backgroundUrl: backgroundUrl,
        backgroundAssetId: data.backgroundAssetId,
      );
    }
    final gender = data.gender;
    if (gender != null) {
      editNext = editNext.copyWith(gender: gender);
    }
    final birthDate = data.birthDate;
    if (birthDate != null) {
      editNext = editNext.copyWith(birthDate: birthDate);
    }
    final regionTagRef = data.regionTagRef;
    if (regionTagRef != null) {
      editNext = editNext.copyWith(
        regionTagRef: regionTagRef,
        region: _regionDisplayFromTagRef(regionTagRef),
      );
    }
    final identityTags = <String>[
      if (data.occupationTagRef != null &&
          data.occupationTagRef!.trim().isNotEmpty)
        data.occupationTagRef!.trim(),
      ...?data.interestTagRefs
          ?.where((tag) => tag.trim().isNotEmpty)
          .map((tag) => tag.trim()),
    ];
    if (data.occupationTagRef != null || data.interestTagRefs != null) {
      next = next.copyWith(identityTags: identityTags);
      editNext = editNext.copyWith(
        identityTags: identityTags,
        occupationTagRef: data.occupationTagRef,
        interestTagRefs: data.interestTagRefs,
      );
    }
    final updatedAt = DateTime.now();
    next = next.copyWith(updatedAt: updatedAt);
    editNext = editNext.copyWith(
      ownerUserId: next.ownerUserId,
      subAccountId: next.subAccountId,
      userHandle: next.userHandle,
      avatarUrl: next.avatarUrl,
      avatarVersion: next.avatarVersion,
      backgroundUrl: next.backgroundUrl,
      nickname: next.nickname.isNotEmpty ? next.nickname : next.displayName,
      displayName: next.displayName,
      bio: next.bio,
      identityTags: next.identityTags,
      updatedAt: updatedAt,
    );
    _profileOverrides[subAccountId] = next;
    _profileEditSnapshotOverrides[subAccountId] = editNext;
  }

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
      // alpha 原型：guest / 空 / owner-like 视角（me / user_001）解析为本人种子作者，
      // 保证「打动」详情页不因 currentUserId 未就绪而空白；其它已登记作者按原 id 取数。
      final resolvedId = _resolveImpactAuthorId(userId);
      final entry = impactByAuthor[resolvedId] ?? impactByAuthor[userId];
      if (entry is Map) {
        return AuthorImpactSummary.fromMap(entry.cast<String, dynamic>());
      }
    }
    return AuthorImpactSummary(authorId: userId);
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String subAccountId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    // 真相源：同一 intersection_core seed 的 AuthorImpactSummary。按 impactId /
    // evidenceSnapshotId 定位对应 AuthorImpactItem，再从该 item 自身派生可枚举明细行
    // （不新造第二套业务列表，R15/R30）；未命中作者或未命中影响 → 空页（不造假）。
    final summary = await getAuthorImpact(subAccountId);
    final item = _matchImpactItem(summary, impactId, evidenceSnapshotId);
    if (item == null) {
      return AuthorImpactEvidencePage(
        impactId: impactId,
        evidenceSnapshotId: evidenceSnapshotId,
      );
    }
    final allRows = _deriveEvidenceRows(item);
    final clampedLimit = limit <= 0
        ? CloudApiDefaults.pageLimit
        : (limit > 50 ? 50 : limit);
    final offset = int.tryParse(cursor) ?? 0;
    final start = offset < 0 ? 0 : offset;
    final end = (start + clampedLimit) > allRows.length
        ? allRows.length
        : (start + clampedLimit);
    final pageItems = start >= allRows.length
        ? const <AuthorImpactEvidenceItem>[]
        : allRows.sublist(start, end);
    final hasMore = end < allRows.length;
    return AuthorImpactEvidencePage(
      impactId: item.impactId,
      evidenceSnapshotId: item.evidenceSnapshotId,
      totalCount: item.count > allRows.length ? item.count : allRows.length,
      items: pageItems,
      nextCursor: hasMore ? '$end' : '',
      hasMore: hasMore,
    );
  }

  static AuthorImpactItem? _matchImpactItem(
    AuthorImpactSummary summary,
    String impactId,
    String evidenceSnapshotId,
  ) {
    final wantedImpact = impactId.trim();
    final wantedSnapshot = evidenceSnapshotId.trim();
    for (final item in summary.items) {
      if (wantedImpact.isNotEmpty && item.impactId == wantedImpact) {
        return item;
      }
      if (wantedSnapshot.isNotEmpty &&
          item.evidenceSnapshotId == wantedSnapshot) {
        return item;
      }
    }
    return null;
  }

  /// 从 seed [AuthorImpactItem] 自身派生可枚举证据行：以其 sampleVisuals（真实样本）为载体，
  /// 不足 count 时补足文本行（representativeActor 文本，无头像），occurredAt 由 freshAt 确定性回推。
  static List<AuthorImpactEvidenceItem> _deriveEvidenceRows(
    AuthorImpactItem item,
  ) {
    final visuals = item.sampleVisuals;
    final target = item.count <= 0 ? visuals.length : item.count;
    final rowCount = target > 12 ? 12 : target; // alpha 上限，避免无意义长列表
    if (rowCount <= 0) {
      return const <AuthorImpactEvidenceItem>[];
    }
    final base = DateTime.tryParse(item.freshAt) ?? DateTime.now().toUtc();
    final summaryText = item.subtitleText.trim().isNotEmpty
        ? item.subtitleText.trim()
        : item.primaryText.trim();
    return List<AuthorImpactEvidenceItem>.generate(rowCount, (i) {
      final occurredAt = base.subtract(Duration(days: i)).toIso8601String();
      return AuthorImpactEvidenceItem(
        evidenceId: '${item.impactId}_ev_$i',
        impactId: item.impactId,
        helpType: item.helpType,
        action: item.action,
        intersectionDimension: item.intersectionDimension,
        occurredAt: occurredAt,
        summaryText: summaryText,
        sampleVisual: i < visuals.length ? visuals[i] : null,
        representativeActor: i == 0 ? item.representativeActor : null,
        actionHints: i == 0
            ? item.actionHints
            : const <IntersectionActionHint>[],
        contentTarget: item.countTarget,
      );
    });
  }

  /// 打动作者归一：空 / owner-like（me/user_001）→ 本人种子作者 fixture_user_current。
  static String _resolveImpactAuthorId(String userId) {
    final trimmed = userId.trim();
    if (trimmed.isEmpty || _ownerLikeSubAccountIds.contains(trimmed)) {
      return 'fixture_user_current';
    }
    return trimmed;
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
          // 趣我圈号(userHandle≈userId) 精确命中 + 昵称/资料模糊，端云语义一致。
          final handle = (user['userId'] ?? '').toString().toLowerCase();
          return handle == normalizedQuery ||
              displayName.toLowerCase().contains(normalizedQuery) ||
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
            avatarVersion: (user['avatarVersion'] as num?)?.toInt() ?? 0,
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
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowingPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractRows = _filterRelationWiresByQuery(
      _contractFollowingWiresFor(userId),
      query: query,
    );
    if (contractRows.isNotEmpty) {
      return _paginateItems(
        contractRows
            .map(
              (m) =>
                  ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                    ProfileSocialRelationRowWireDto.fromMap(m),
                  ),
            )
            .toList(growable: false),
        cursor: cursor,
        limit: limit,
      );
    }
    final filtered = _filterRelationWiresByQuery(
      _mockFollowingWiresFor(userId),
      query: query,
    );
    return _paginateItems(
      filtered
          .map(
            (m) =>
                ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                  ProfileSocialRelationRowWireDto.fromMap(m),
                ),
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
    );
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowersPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final contractRows = _filterRelationWiresByQuery(
      _contractFollowerWiresFor(userId),
      query: query,
    );
    if (contractRows.isNotEmpty) {
      return _paginateItems(
        contractRows
            .map(
              (m) =>
                  ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                    ProfileSocialRelationRowWireDto.fromMap(m),
                  ),
            )
            .toList(growable: false),
        cursor: cursor,
        limit: limit,
      );
    }
    final filtered = _filterRelationWiresByQuery(
      _mockFollowerWiresFor(userId),
      query: query,
    );
    return _paginateItems(
      filtered
          .map(
            (m) =>
                ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                  ProfileSocialRelationRowWireDto.fromMap(m),
                ),
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
    );
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
  Future<CursorPage<ProfileInteractionActivityViewData>>
  listProfileShareInteractions(
    String subAccountId, {
    required String direction,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet(
      'profile_share_interaction_core',
    );
    final rawItems = seed?['profileShareInteractions'];
    if (rawItems is! List) {
      return const CursorPage<ProfileInteractionActivityViewData>(
        items: <ProfileInteractionActivityViewData>[],
      );
    }
    final all =
        rawItems
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .where(
              (item) =>
                  item['ownerSubAccountId']?.toString() == subAccountId &&
                  item['direction']?.toString() == direction,
            )
            .map(
              (item) =>
                  ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
                    ProfileInteractionActivityWireDto.fromMap(item),
                  ),
            )
            .toList(growable: false)
          ..sort((a, b) {
            final byTime = (b.occurredAt ?? b.createdAt ?? DateTime(1970))
                .compareTo(a.occurredAt ?? a.createdAt ?? DateTime(1970));
            return byTime != 0 ? byTime : b.activityId.compareTo(a.activityId);
          });
    final cursorIndex = cursor == null
        ? -1
        : all.indexWhere((item) => item.activityId == cursor);
    final start = cursorIndex < 0 ? 0 : cursorIndex + 1;
    final end = (start + limit).clamp(0, all.length);
    final pageItems = start >= all.length
        ? const <ProfileInteractionActivityViewData>[]
        : all.sublist(start, end);
    return CursorPage<ProfileInteractionActivityViewData>(
      items: pageItems,
      nextCursor: end < all.length && pageItems.isNotEmpty
          ? pageItems.last.activityId
          : null,
    );
  }

  @override
  Future<void> markProfileShareInteractionState(
    String subAccountId,
    String interactionId, {
    required String state,
  }) async {}

  @override
  Future<List<PersonaManagementItemWireDto>> listPersonas() async {
    final contractPersonas = _contractPersonaRows();
    if (contractPersonas.isNotEmpty) {
      return contractPersonas.map(_personaDtoFromWire).toList(growable: false);
    }
    return const <PersonaManagementItemWireDto>[];
  }

  @override
  Future<PersonaManagementItemWireDto> createPersona(
    PersonaCreateRequestDto request,
  ) async {
    final wire = _omitNullMapValues(request.toMap());
    final isolation = request.isolationLevel;
    final isPrivate = isolation == 'strict';
    return _personaDtoFromWire(<String, dynamic>{
      'subAccountId': 'new_persona_1',
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
        .where((item) => ids.contains(item['postId']))
        .map(contentPostDtoFromReadModelMap)
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

  static final Map<String, Map<String, dynamic>>
  _contractRelationshipByTargetUserId = {
    for (final item in _contractRelationshipRows())
      item['targetUserId'].toString(): <String, dynamic>{
        'relationState': item['mutualFollow'] == true
            ? 'mutual'
            : item['following'] == true
            ? 'following'
            : 'not_following',
        'isFollowing': item['following'] == true,
        'isFollowedBy': item['mutualFollow'] == true,
        'isMutual': item['mutualFollow'] == true,
      },
  };
}

// ─── Remote 实现（调用云侧 API）───────────────────────────────────────────────
