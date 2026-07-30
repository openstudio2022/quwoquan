part of '../alpha_user_profile_repository.dart';

class MockUserProfileRepository
    implements
        ProfileQuery,
        ProfileEditQuery,
        AuthorImpactQuery,
        PersonaRelationshipQuery,
        PersonaRelationshipCommandWriter {
  const MockUserProfileRepository();

  /// 本人在 mock 下保存的资料覆盖（开发态进程内持久化）。
  ///
  /// key = personaId；value = 合并后的完整 wire。保存成功后 [getUserProfile]
  /// 立即读到同一真相源，保证「我的主页」即时回显新昵称 / 简介 / 头像 / 封面，
  /// 不再是空实现导致的「保存后无变化」。
  static final Map<String, PersonaProfileWireDto> _profileOverrides =
      <String, PersonaProfileWireDto>{};

  /// 本人编辑页私有快照覆盖。
  ///
  /// 公开主页 wire 不承载生日、性别、地区等私有编辑字段；这些字段必须在
  /// ProfileEditSnapshotWire 维度独立往返，避免编辑页再次进入时退回空值。
  static final _ProfileEditSnapshotOverrideMap _profileEditSnapshotOverrides =
      _ProfileEditSnapshotOverrideMap();
  static final List<Map<String, dynamic>> _mockPersonaRows =
      _contractPersonaRows().map(Map<String, dynamic>.from).toList();

  /// 解析某个用户的基础 wire（覆盖优先，其次契约种子，最后默认档案）。
  PersonaProfileWireDto _baseProfileWire(String userId) {
    final override = _profileOverrides[userId];
    if (override != null) {
      return _normalizeCurrentUserVariantWire(userId, override);
    }
    if (_ownerLikePersonaIds.contains(userId)) {
      final currentOverride = _profileOverrides[kMockCurrentPersonaId];
      if (currentOverride != null) {
        return _normalizeCurrentUserVariantWire(userId, currentOverride);
      }
    }
    return _normalizeCurrentUserVariantWire(
      userId,
      resolveMockUserProfileWire(userId),
    );
  }

  PersonaProfileWireDto _normalizeCurrentUserVariantWire(
    String requestedId,
    PersonaProfileWireDto wire,
  ) {
    if (!_ownerLikePersonaIds.contains(requestedId)) {
      return wire;
    }
    return wire.copyWith(
      ownerUserId: kMockCurrentOwnerId,
      personaId: kMockCurrentPersonaId,
    );
  }

  @override
  Future<PersonaProfileViewData> getUserProfile(String userId) async {
    return PersonaProfileViewData.fromPersonaProfileWire(
      _baseProfileWire(userId),
    );
  }

  /// Mock 本人态判定（开发态约定）：'me' 或 contract 当前用户视为本人。
  static Set<String> get _ownerLikePersonaIds => {
    'me',
    'fixture_user_current',
    'user_001',
    AlphaFixtureUserResolver.currentUserVariantPersonaId,
    AlphaFixtureUserResolver.currentUserVariantUserId,
  };

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String personaId,
  ) async {
    final resolvedId = AlphaFixtureUserResolver.resolvePersonaId(personaId);
    final profile = await getUserProfile(resolvedId);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    final isOwner =
        _ownerLikePersonaIds.contains(personaId) ||
        _ownerLikePersonaIds.contains(resolvedId);
    final relation = await getRelationship(resolvedId);
    final viewerPersonaId = isOwner
        ? resolvedId
        : AlphaFixtureUserResolver.currentUserVariantPersonaId;
    final relationshipCapability = isOwner
        ? null
        : _fixtureRelationshipCapability(
            viewerId: viewerPersonaId,
            targetId: personaId,
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
        viewerPersonaId: viewerPersonaId,
        isOwner: isOwner,
        isGuest: false,
        relationToTarget: isOwner ? 'self' : relation.relationState,
        canViewFullProfile: true,
      ),
      cacheVersion:
          'mock-${profile.personaId}-${profile.updatedAt?.toIso8601String() ?? 'static'}',
    );
  }

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    final profile = await getUserProfile(kMockCurrentPersonaId);
    final credentials = await listCredentialsForProfileEdit();
    final base = ProfileEditSnapshotData.fromProfile(
      profile: profile,
      credentials: credentials,
    );
    final override = _resolveMockProfileEditSnapshotWire(kMockCurrentPersonaId);
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
    final personaId = hit?['userId']?.toString() ?? normalizedHandle;
    return ProfileQrResolveWireDto(
      personaId: personaId,
      userHandle: personaId,
      publicProfileUrl: 'https://quwoquan.com/u/$personaId',
      scanStatus: 'accepted',
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    final profile = await getUserProfile(userId);
    return UserProfileStatsViewData.fromProfile(profile);
  }

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String userId) async {
    // Contract seed（intersection_core.authorImpact）驱动；无 seed/未登记作者时返回空摘要（不造假）。
    final seed = objectScenarioSeedReader.contentSeedSet('intersection_core');
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
    return AuthorImpactSummary(
      authorId: userId,
      total: 0,
      items: const <AuthorImpactItem>[],
    );
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String personaId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    // 真相源：同一 intersection_core seed 的 AuthorImpactSummary。按 impactId /
    // evidenceSnapshotId 定位对应 AuthorImpactItem，再从该 item 自身派生可枚举明细行
    // （不新造第二套业务列表，R15/R30）；未命中作者或未命中影响 → 空页（不造假）。
    final summary = await getAuthorImpact(personaId);
    final item = _matchImpactItem(summary, impactId, evidenceSnapshotId);
    if (item == null) {
      return AuthorImpactEvidencePage(
        impactId: impactId,
        evidenceSnapshotId: evidenceSnapshotId,
        totalCount: 0,
        items: const <AuthorImpactEvidenceItem>[],
        nextCursor: '',
        hasMore: false,
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
    if (trimmed.isEmpty || _ownerLikePersonaIds.contains(trimmed)) {
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
          final personaId = user['userId']?.toString() ?? '';
          final relationship = _contractRelationshipByTargetUserId[personaId];
          final relationState =
              relationship?['relationState']?.toString() ?? 'not_following';
          final isFollowing = relationship?['isFollowing'] == true;
          final hasFormalConversation =
              relationState == 'mutual' || isFollowing;
          final wire = SocialRelationSearchItemWireDto(
            personaId: personaId,
            userHandle: personaId,
            displayName: (user['displayName'] ?? personaId).toString(),
            avatarUrl: user['avatarUrl']?.toString(),
            avatarVersion: (user['avatarVersion'] as num?)?.toInt() ?? 0,
            headline: (user['bio'] ?? '').toString(),
            chatAvailable: hasFormalConversation,
            relationshipCapability: RelationshipCapabilityWireDto(
              viewerPersonaId: kMockCurrentPersonaId,
              targetPersonaId: personaId,
              relationState: relationState,
              canFollow: !isFollowing,
              canUnfollow: isFollowing,
              canFollowBack: relationState == 'followed_by',
              canOpenConversation: hasFormalConversation,
            ),
          );
          return SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
            wire,
          );
        })
        .toList(growable: false);
  }

  Future<void> followUser(
    String targetUserId, {
    String? ownerUserId,
    String? personaId,
    String? personaContextVersion,
  }) async {
    _contractRelationshipByTargetUserId[targetUserId] = <String, dynamic>{
      'relationState': 'following',
      'isFollowing': true,
      'isFollowedBy': false,
      'isMutual': false,
    };
  }

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) {
    return followUser(targetPersonaId);
  }

  Future<void> unfollowUser(
    String targetUserId, {
    String? ownerUserId,
    String? personaId,
    String? personaContextVersion,
  }) async {
    _contractRelationshipByTargetUserId[targetUserId] = <String, dynamic>{
      'relationState': 'not_following',
      'isFollowing': false,
      'isFollowedBy': false,
      'isMutual': false,
    };
  }

  @override
  Future<void> unfollow(String targetPersonaId) {
    return unfollowUser(targetPersonaId);
  }

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
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return listFollowingPage(
      personaId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
  }

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
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return listFollowersPage(
      personaId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
  }

  Future<RelationshipViewData> getRelationship(String userId) async {
    final contractRelationship = _contractRelationshipByTargetUserId[userId];
    if (contractRelationship != null) {
      return RelationshipViewData.fromRelationshipViewWire(
        _relationshipViewFromRaw(contractRelationship),
      );
    }
    return const RelationshipViewData(relationState: 'not_following');
  }

  Future<List<PersonaManagementItemWireDto>> listPersonas() async {
    if (_mockPersonaRows.isNotEmpty) {
      return _mockPersonaRows.map(_personaDtoFromWire).toList(growable: false);
    }
    return const <PersonaManagementItemWireDto>[];
  }

  Future<PersonaManagementItemWireDto> createPersona(
    PersonaCreateRequestDto request,
  ) async {
    final wire = _omitNullMapValues(request.toMap());
    final isolation = request.isolationLevel;
    final isPrivate = isolation == 'strict';
    final row = <String, dynamic>{
      'personaId': 'new_persona_${_mockPersonaRows.length + 1}',
      ...wire,
      'isActive': false,
      'isPrimary': false,
      'isPrivate': isPrivate,
    };
    _mockPersonaRows.add(row);
    return _personaDtoFromWire(row);
  }

  Future<void> updatePersona(
    String personaId,
    PersonaUpdateRequestDto request,
  ) async {
    final index = _mockPersonaRows.indexWhere(
      (item) => item['personaId'] == personaId,
    );
    if (index < 0) {
      throw StateError('persona not found');
    }
    _mockPersonaRows[index] = <String, dynamic>{
      ..._mockPersonaRows[index],
      ..._omitNullMapValues(request.toMap()),
      'personaId': personaId,
    };
  }

  Future<void> activatePersona(String personaId) async {
    final index = _mockPersonaRows.indexWhere(
      (item) => item['personaId'] == personaId,
    );
    if (index < 0) {
      throw StateError('persona not found');
    }
    for (var i = 0; i < _mockPersonaRows.length; i++) {
      _mockPersonaRows[i] = <String, dynamic>{
        ..._mockPersonaRows[i],
        'isActive': i == index,
      };
    }
  }

  // ── Mock 数据 ─────────────────────────────────────────────────────────────

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

RelationshipCapabilityDto _fixtureRelationshipCapability({
  required String viewerId,
  required String targetId,
  required bool isFollowing,
  required bool isFollowedBy,
  bool hasFormalConversation = false,
}) {
  final isMutual = isFollowing && isFollowedBy;
  final relationState = isMutual
      ? 'mutual'
      : isFollowing
      ? 'following'
      : isFollowedBy
      ? 'followed_by'
      : 'not_following';
  return RelationshipCapabilityDto(
    viewerPersonaId: viewerId,
    targetPersonaId: targetId,
    relationState: relationState,
    canFollow: !isFollowing,
    canUnfollow: isFollowing,
    canFollowBack: isFollowedBy && !isFollowing,
    canGreet: !isMutual && !hasFormalConversation,
    canOpenConversation: isMutual || hasFormalConversation,
    canCreateDirectConversation: isMutual,
    canSendMessage: isMutual || hasFormalConversation,
    hasPendingGreeting: false,
    hasFormalConversation: hasFormalConversation,
    canStartVoiceCall: isMutual,
    canStartVideoCall: isMutual,
    isBlocked: false,
    isBlockedBy: false,
  );
}
