part of "profile_homepage_models.dart";

/// 清单用户档案展示面别名：端侧统一 [SubAccountProfileViewData]（与 codegen UserProfileDto wire 对齐由 Repository 负责）。
typedef UserProfileViewData = SubAccountProfileViewData;

/// 清单 PersonaDto：端侧管理行统一 [PersonaManagementItemViewData]。
typedef PersonaDtoSurface = PersonaManagementItemViewData;

@immutable
class ProfileInteractionActivityViewData {
  const ProfileInteractionActivityViewData({
    required this.activityId,
    required this.activityType,
    required this.direction,
    required this.commentKind,
    required this.commentId,
    required this.parentCommentId,
    this.viewerReaction = 'none',
    required this.actorSubAccountId,
    required this.actorDisplayName,
    required this.actorAvatarUrl,
    this.actorAvatarVersion = 0,
    this.counterpartSubAccountId = '',
    this.counterpartDisplayName = '',
    this.counterpartAvatarUrl = '',
    required this.targetSubAccountId,
    required this.targetContentId,
    required this.targetContentType,
    required this.targetContentSummary,
    this.targetKind = 'record',
    this.targetAvailability = 'active',
    this.targetReplyCount = 0,
    required this.displaySubAccountId,
    required this.displayName,
    required this.displayAvatarUrl,
    this.displayAvatarVersion = 0,
    required this.displayUserRouteId,
    required this.primaryText,
    required this.contextText,
    required this.previewMediaKind,
    required this.previewImageUrl,
    required this.previewText,
    required this.previewUnavailable,
    required this.previewObjectId,
    required this.previewRouteId,
    this.outboundShareEventId = '',
    this.shareText = '',
    this.impactPrimaryText = '',
    this.impactDeepLink = '',
    required this.filterKeys,
    required this.createdAt,
    this.occurredAt,
    this.seenAt,
    this.readAt,
  });

  final String activityId;
  final String activityType;
  final String direction;
  final String commentKind;
  final String commentId;
  final String parentCommentId;

  /// 浏览者（当前登录用户）对该条评论/回复的反应：none/like/dislike。
  /// 用于「我的主页·互动」内联赞↔已赞态展示。
  final String viewerReaction;
  final String actorSubAccountId;
  final String actorDisplayName;
  final String actorAvatarUrl;
  final int actorAvatarVersion;
  final String counterpartSubAccountId;
  final String counterpartDisplayName;
  final String counterpartAvatarUrl;
  final String targetSubAccountId;
  final String targetContentId;
  final String targetContentType;
  final String targetContentSummary;
  final String targetKind;
  final String targetAvailability;
  final int targetReplyCount;
  final String displaySubAccountId;
  final String displayName;
  final String displayAvatarUrl;
  final int displayAvatarVersion;
  final String displayUserRouteId;
  final String primaryText;
  final String contextText;
  final String previewMediaKind;
  final String previewImageUrl;
  final String previewText;
  final bool previewUnavailable;
  final String previewObjectId;
  final String previewRouteId;

  /// 不可变站外分享事实的事件标识，仅用于追踪，不能作为可导航内容。
  final String outboundShareEventId;
  final String shareText;
  final String impactPrimaryText;
  final String impactDeepLink;
  final List<String> filterKeys;
  final DateTime? createdAt;
  final DateTime? occurredAt;
  final DateTime? seenAt;
  final DateTime? readAt;

  factory ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
    ProfileInteractionActivityWireDto w,
  ) {
    var activityId = w.activityId;
    if (activityId.isEmpty) {
      final prefix = w.activityType.isEmpty ? 'activity' : w.activityType;
      activityId = '$prefix:${w.actorSubAccountId}';
    }
    final actorDisplayName = w.actorDisplayName.isNotEmpty
        ? w.actorDisplayName
        : w.actorSubAccountId;
    final displaySubAccountId = w.displaySubAccountId.isNotEmpty
        ? w.displaySubAccountId
        : w.actorSubAccountId;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : (actorDisplayName.isNotEmpty
              ? actorDisplayName
              : displaySubAccountId);
    final displayAvatarUrl = w.displayAvatarUrl.isNotEmpty
        ? w.displayAvatarUrl
        : w.actorAvatarUrl;
    final actorAvatarVersion = w.actorAvatarVersion;
    final displayAvatarVersion = w.displayAvatarVersion > 0
        ? w.displayAvatarVersion
        : (displayAvatarUrl == w.actorAvatarUrl ? w.actorAvatarVersion : 0);
    final primaryText = w.primaryText;
    final previewObjectId = w.previewObjectId.isNotEmpty
        ? w.previewObjectId
        : w.targetContentId;
    final previewMediaKind = w.previewMediaKind.isNotEmpty
        ? w.previewMediaKind
        : 'none';
    final filterKeys = <String>{
      'all',
      ...w.filterKeys.map((key) => key.trim()).where((key) => key.isNotEmpty),
    }.toList(growable: false);
    final actorAvatarUrl = resolveAvatarImageUrl(
      w.actorAvatarUrl,
      avatarVersion: actorAvatarVersion,
    );
    final resolvedDisplayAvatarUrl = resolveAvatarImageUrl(
      displayAvatarUrl,
      avatarVersion: displayAvatarVersion,
    );
    final previewImageUrl = resolveContentMediaUrl(w.previewImageUrl);
    return ProfileInteractionActivityViewData(
      activityId: activityId,
      activityType: w.activityType,
      direction: w.direction,
      commentKind: w.commentKind,
      commentId: w.commentId,
      parentCommentId: w.parentCommentId,
      viewerReaction: w.viewerReaction,
      actorSubAccountId: w.actorSubAccountId,
      actorDisplayName: actorDisplayName,
      actorAvatarUrl: actorAvatarUrl,
      actorAvatarVersion: actorAvatarVersion,
      counterpartSubAccountId: w.counterpartSubAccountId,
      counterpartDisplayName: w.counterpartDisplayName,
      counterpartAvatarUrl: resolveAvatarImageUrl(w.counterpartAvatarUrl),
      targetSubAccountId: w.targetSubAccountId,
      targetContentId: w.targetContentId,
      targetContentType: w.targetContentType,
      targetContentSummary: w.targetContentSummary,
      targetKind: w.targetKind,
      targetAvailability: w.targetAvailability,
      targetReplyCount: w.targetReplyCount,
      displaySubAccountId: displaySubAccountId,
      displayName: displayName,
      displayAvatarUrl: resolvedDisplayAvatarUrl,
      displayAvatarVersion: displayAvatarVersion,
      displayUserRouteId: w.displayUserRouteId,
      primaryText: primaryText,
      contextText: w.contextText,
      previewMediaKind: previewMediaKind,
      previewImageUrl: previewImageUrl,
      previewText: w.previewText,
      previewUnavailable: w.previewUnavailable,
      previewObjectId: previewObjectId,
      previewRouteId: w.previewRouteId,
      outboundShareEventId: w.outboundShareEventId,
      shareText: w.shareText,
      impactPrimaryText: w.impactPrimaryText,
      impactDeepLink: w.impactDeepLink,
      filterKeys: filterKeys,
      createdAt: w.createdAt,
      occurredAt: w.occurredAt,
      seenAt: w.seenAt,
      readAt: w.readAt,
    );
  }

  @Deprecated(
    'Use fromProfileInteractionActivityWire(ProfileInteractionActivityWireDto)',
  )
  factory ProfileInteractionActivityViewData.fromMap(Map<String, dynamic> map) {
    return ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
      ProfileInteractionActivityWireDto.fromMap(map),
    );
  }
}

@immutable
class ActivePersonaContextViewData {
  const ActivePersonaContextViewData({
    required this.subAccountId,
    required this.ownerUserId,
    required this.subjectType,
    required this.displayName,
    required this.avatarUrl,
    this.avatarVersion = 0,
    required this.personaContextVersion,
    this.isPrimary = false,
    this.isFallback = false,
  });

  final String subAccountId;
  final String ownerUserId;
  final String subjectType;
  final String displayName;
  final String avatarUrl;
  final int avatarVersion;
  final String personaContextVersion;
  final bool isPrimary;
  final bool isFallback;

  String get contextVersion => personaContextVersion;

  String get personaSnapshotVersion => '1';

  bool get hasSubAccount => subAccountId.isNotEmpty;

  Map<String, Object?> toTypedEnvelope({
    String sourceSurfaceId = '',
    bool explicitOverride = false,
  }) {
    return <String, Object?>{
      'subAccountId': subAccountId,
      if (contextVersion.isNotEmpty) 'contextVersion': contextVersion,
      if (personaContextVersion.isNotEmpty)
        'personaContextVersion': personaContextVersion,
      'personaSnapshotVersion': personaSnapshotVersion,
      if (sourceSurfaceId.trim().isNotEmpty)
        'sourceSurfaceId': sourceSurfaceId.trim(),
      'explicitOverride': explicitOverride,
    };
  }

  factory ActivePersonaContextViewData.fromActivePersonaContextWire(
    ActivePersonaContextWireDto w,
  ) {
    final subAccountId = w.subAccountId;
    var ownerUserId = w.ownerUserId;
    if (ownerUserId.isEmpty) {
      ownerUserId = subAccountId;
    }
    final displayName = w.displayName.isNotEmpty ? w.displayName : subAccountId;
    final subjectType = w.subjectType.isNotEmpty ? w.subjectType : 'subAccount';
    return ActivePersonaContextViewData(
      subAccountId: subAccountId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: resolveAvatarImageUrl(
        w.avatarUrl,
        avatarVersion: w.avatarVersion,
      ),
      avatarVersion: w.avatarVersion,
      personaContextVersion: w.personaContextVersion,
      isPrimary: w.isPrimary,
    );
  }

  @Deprecated('Use fromActivePersonaContextWire(ActivePersonaContextWireDto)')
  factory ActivePersonaContextViewData.fromMap(Map<String, dynamic> map) {
    return ActivePersonaContextViewData.fromActivePersonaContextWire(
      ActivePersonaContextWireDto.fromMap(map),
    );
  }

  factory ActivePersonaContextViewData.fallback({
    required String subAccountId,
    required String ownerUserId,
    required String displayName,
    required String avatarUrl,
    int avatarVersion = 0,
    String subjectType = 'subAccount',
    String personaContextVersion = '',
  }) {
    return ActivePersonaContextViewData(
      subAccountId: subAccountId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: avatarUrl,
      avatarVersion: avatarVersion,
      personaContextVersion: personaContextVersion,
      isFallback: true,
    );
  }
}

@immutable
class PersonaManagementItemViewData {
  const PersonaManagementItemViewData({
    required this.subAccountId,
    required this.displayName,
    required this.userHandle,
    required this.phone,
    required this.email,
    required this.avatarUrl,
    this.avatarVersion = 0,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.isPrimary,
    required this.isActive,
    required this.status,
    required this.retiredAt,
    required this.hasAttributedHistory,
    required this.hasPublishedContent,
    required this.inheritsProfileFromOwner,
    required this.overriddenProfileFields,
    required this.lastProfileSyncAt,
    required this.lastProfileSyncSource,
    required this.lastActivatedAt,
    required this.subjectType,
  });

  final String subAccountId;
  final String displayName;
  final String userHandle;
  final String phone;
  final String email;
  final String avatarUrl;
  final int avatarVersion;
  final String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  final bool isActive;
  final String status;
  final DateTime? retiredAt;
  final bool hasAttributedHistory;
  final bool hasPublishedContent;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final DateTime? lastProfileSyncAt;
  final String lastProfileSyncSource;
  final DateTime? lastActivatedAt;
  final String subjectType;

  bool get hasContactInfo => phone.isNotEmpty || email.isNotEmpty;
  bool get isRetired => status == 'retired';

  /// 纠正 wire 默认 `subjectType: persona`：无 `subAccountId` 时视为 user 主行。
  factory PersonaManagementItemViewData.fromPersonaManagementItemWire(
    PersonaManagementItemWireDto w,
  ) {
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : w.subAccountId;
    final subjectType = w.subAccountId.isEmpty
        ? (w.subjectType.isEmpty || w.subjectType == 'persona'
              ? 'user'
              : w.subjectType)
        : (w.subjectType.isNotEmpty ? w.subjectType : 'persona');
    return PersonaManagementItemViewData(
      subAccountId: w.subAccountId,
      displayName: displayName,
      userHandle: w.userHandle,
      phone: w.phone,
      email: w.email,
      avatarUrl: resolveAvatarImageUrl(
        w.avatarUrl,
        avatarVersion: w.avatarVersion,
      ),
      avatarVersion: w.avatarVersion,
      isolationLevel: w.isolationLevel,
      profileVisibility: w.profileVisibility,
      isPrimary: w.isPrimary,
      isActive: w.isActive,
      status: w.status,
      retiredAt: w.retiredAt,
      hasAttributedHistory: w.hasAttributedHistory,
      hasPublishedContent: w.hasPublishedContent,
      inheritsProfileFromOwner: w.inheritsProfileFromOwner,
      overriddenProfileFields: w.overriddenProfileFields,
      lastProfileSyncAt: w.lastProfileSyncAt,
      lastProfileSyncSource: w.lastProfileSyncSource,
      lastActivatedAt: w.lastActivatedAt,
      subjectType: subjectType,
    );
  }

  @Deprecated('Use fromPersonaManagementItemWire(PersonaManagementItemWireDto)')
  factory PersonaManagementItemViewData.fromMap(Map<String, dynamic> map) {
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto.fromMap(map),
    );
  }
}

@immutable
class PersonaSyncSuggestionViewData {
  const PersonaSyncSuggestionViewData({
    required this.sourcePersonaId,
    required this.sourceDisplayName,
    required this.targetPersonaIds,
    required this.targetDisplayNames,
    required this.fieldKeys,
  });

  final String sourcePersonaId;
  final String sourceDisplayName;
  final List<String> targetPersonaIds;
  final List<String> targetDisplayNames;
  final List<String> fieldKeys;

  bool get canApply => targetPersonaIds.isNotEmpty && fieldKeys.isNotEmpty;
}

@immutable
class PersonaManagementQuotaViewData {
  const PersonaManagementQuotaViewData({
    required this.maxSubAccounts,
    required this.usedSubAccounts,
  });

  final int maxSubAccounts;
  final int usedSubAccounts;

  int get remainingSlots {
    final remaining = maxSubAccounts - usedSubAccounts;
    return remaining < 0 ? 0 : remaining;
  }

  bool get quotaReached => usedSubAccounts >= maxSubAccounts;

  factory PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
    PersonaManagementQuotaWireDto w,
  ) {
    var max = w.maxSubAccounts;
    if (max <= 0) max = 5;
    return PersonaManagementQuotaViewData(
      maxSubAccounts: max,
      usedSubAccounts: w.usedSubAccounts,
    );
  }

  @Deprecated(
    'Use fromPersonaManagementQuotaWire(PersonaManagementQuotaWireDto)',
  )
  factory PersonaManagementQuotaViewData.fromMap(Map<String, dynamic> map) {
    return PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
      PersonaManagementQuotaWireDto.fromMap(map),
    );
  }
}

@immutable
class PersonaLifecycleGuardViewData {
  const PersonaLifecycleGuardViewData({
    required this.subAccountId,
    required this.canDelete,
    required this.canRetire,
    required this.requiredAction,
    required this.reasonCode,
    required this.message,
  });

  final String subAccountId;
  final bool canDelete;
  final bool canRetire;
  final String requiredAction;
  final String reasonCode;
  final String message;

  factory PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
    PersonaLifecycleGuardWireDto w,
  ) {
    return PersonaLifecycleGuardViewData(
      subAccountId: w.subAccountId,
      canDelete: w.canDelete,
      canRetire: w.canRetire,
      requiredAction: w.requiredAction,
      reasonCode: w.reasonCode,
      message: w.message,
    );
  }

  @Deprecated('Use fromPersonaLifecycleGuardWire(PersonaLifecycleGuardWireDto)')
  factory PersonaLifecycleGuardViewData.fromMap(Map<String, dynamic> map) {
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
      PersonaLifecycleGuardWireDto.fromMap(map),
    );
  }
}

@immutable
class PersonaManagementSummaryViewData {
  const PersonaManagementSummaryViewData({
    required this.items,
    required this.quota,
    this.activeContext,
  });

  final List<PersonaManagementItemViewData> items;
  final PersonaManagementQuotaViewData quota;
  final ActivePersonaContextViewData? activeContext;

  factory PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
    PersonaManagementSummaryWireDto w,
  ) {
    final items = w.items
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
    final quotaMap =
        w.quota ??
        <String, dynamic>{'usedSubAccounts': items.length, 'maxSubAccounts': 5};
    final activeMap = w.activeContext;
    return PersonaManagementSummaryViewData(
      items: items,
      quota: PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
        PersonaManagementQuotaWireDto.fromMap(quotaMap),
      ),
      activeContext: activeMap == null
          ? null
          : ActivePersonaContextViewData.fromActivePersonaContextWire(
              ActivePersonaContextWireDto.fromMap(activeMap),
            ),
    );
  }

  @Deprecated(
    'Use fromPersonaManagementSummaryWire(PersonaManagementSummaryWireDto)',
  )
  factory PersonaManagementSummaryViewData.fromMap(Map<String, dynamic> map) {
    return PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
      PersonaManagementSummaryWireDto.fromMap(map),
    );
  }
}

// ─── 主页 Tab 行模型（与 mock 数据字段对齐；待 service.yaml codegen 收敛）────────

/// 作品集条目。
@immutable
class UserWorkItem {
  const UserWorkItem({
    required this.id,
    required this.type,
    required this.title,
    required this.coverUrl,
    required this.likeCount,
    required this.date,
    required this.desc,
  });

  final String id;
  final String type;
  final String title;
  final String coverUrl;
  final int likeCount;
  final String date;
  final String desc;
}

/// 生活记录条目。字段与后端契约 `user/user_life_item`（UserLifeItemDto）一一对齐。
/// category 为 LifeItemCategory 枚举值（footprint/soul/taste/private），子页过滤直接比对。
@immutable
class UserLifeItem {
  const UserLifeItem({
    required this.id,
    required this.category,
    required this.title,
    this.subtitle = '',
    this.imageUrl = '',
    this.refId = '',
  });

  final String id;

  /// LifeItemCategory 枚举值：footprint=足迹 / soul=书影音 / taste=味蕾 / private=爱物。
  final String category;

  /// 记录主文案。
  final String title;

  /// 记录副标题/描述。
  final String subtitle;

  /// 封面图（绝对 URL 或对象键）。
  final String imageUrl;

  /// 关联内容引用（作品/圈子等）。
  final String refId;
}

// ─── 主页首屏聚合（homepage-bundle，锁定决策 #1：一次聚合 + 交集/打动并发补充）──
