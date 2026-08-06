import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ActivePersonaContextViewData {
  const ActivePersonaContextViewData({
    required this.personaId,
    required this.ownerUserId,
    required this.subjectType,
    required this.displayName,
    required this.avatarUrl,
    this.avatarVersion = 0,
    this.contextVersion = 1,
    this.personaSnapshotVersion = 1,
    this.isPrimary = false,
    this.isFallback = false,
  });

  final String personaId;
  final String ownerUserId;
  final String subjectType;
  final String displayName;
  final String avatarUrl;
  final int avatarVersion;
  final int contextVersion;
  final int personaSnapshotVersion;
  final bool isPrimary;
  final bool isFallback;

  bool get hasPersona => personaId.isNotEmpty;

  Map<String, Object?> toTypedEnvelope({
    String sourceSurfaceId = '',
    bool explicitOverride = false,
  }) {
    return <String, Object?>{
      'personaId': personaId,
      if (contextVersion > 0) 'contextVersion': contextVersion,
      'personaSnapshotVersion': personaSnapshotVersion,
      if (sourceSurfaceId.trim().isNotEmpty)
        'sourceSurfaceId': sourceSurfaceId.trim(),
      'explicitOverride': explicitOverride,
    };
  }

  factory ActivePersonaContextViewData.fallback({
    required String personaId,
    required String ownerUserId,
    required String displayName,
    required String avatarUrl,
    int avatarVersion = 0,
    String subjectType = 'persona',
    int contextVersion = 1,
    int personaSnapshotVersion = 1,
  }) {
    return ActivePersonaContextViewData(
      personaId: personaId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: avatarUrl,
      avatarVersion: avatarVersion,
      contextVersion: contextVersion,
      personaSnapshotVersion: personaSnapshotVersion,
      isFallback: true,
    );
  }
}

class PersonaManagementItemViewData {
  const PersonaManagementItemViewData({
    required this.personaId,
    required this.displayName,
    required this.userHandle,
    required this.avatarUrl,
    this.avatarVersion = 0,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.isPrimary,
    required this.isActive,
    required this.status,
    required this.retiredAt,
    required this.hasPublishedContent,
    required this.inheritsProfileFromOwner,
    required this.overriddenProfileFields,
    required this.lastProfileSyncAt,
    required this.lastProfileSyncSource,
    required this.lastActivatedAt,
    required this.subjectType,
  });

  final String personaId;
  final String displayName;
  final String userHandle;
  final String avatarUrl;
  final int avatarVersion;
  final String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  final bool isActive;
  final String status;
  final DateTime? retiredAt;
  final bool hasPublishedContent;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final DateTime? lastProfileSyncAt;
  final String lastProfileSyncSource;
  final DateTime? lastActivatedAt;
  final String subjectType;

  bool get isRetired => status == 'retired';
}

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

class PersonaManagementQuotaViewData {
  const PersonaManagementQuotaViewData({
    required this.maxPersonas,
    required this.usedPersonas,
  });

  final int maxPersonas;
  final int usedPersonas;

  int get remainingSlots {
    final remaining = maxPersonas - usedPersonas;
    return remaining < 0 ? 0 : remaining;
  }

  bool get quotaReached => usedPersonas >= maxPersonas;

  factory PersonaManagementQuotaViewData.fromWire(
    PersonaManagementQuotaView projection,
  ) {
    final max = projection.quotaLimit <= 0 ? 5 : projection.quotaLimit;
    return PersonaManagementQuotaViewData(
      maxPersonas: max,
      usedPersonas: projection.totalCount,
    );
  }
}

class PersonaLifecycleGuardViewData {
  const PersonaLifecycleGuardViewData({
    required this.personaId,
    required this.requestedAction,
    required this.allowed,
    required this.reason,
    required this.requiresSuccessor,
  });

  final String personaId;
  final String requestedAction;
  final bool allowed;
  final String reason;
  final bool requiresSuccessor;

  factory PersonaLifecycleGuardViewData.fromWire(
    PersonaLifecycleGuardView projection,
  ) {
    return PersonaLifecycleGuardViewData(
      personaId: projection.personaId,
      requestedAction: projection.requestedAction.wireName,
      allowed: projection.allowed,
      reason: projection.reason.wireName,
      requiresSuccessor: projection.requiresSuccessor,
    );
  }
}

class PersonaManagementSummaryViewData {
  const PersonaManagementSummaryViewData({
    required this.items,
    required this.quota,
    this.activeContext,
  });

  final List<PersonaManagementItemViewData> items;
  final PersonaManagementQuotaViewData quota;
  final ActivePersonaContextViewData? activeContext;
}

// ─── 主页首屏聚合（homepage-bundle，锁定决策 #1：一次聚合 + 交集/打动并发补充）──
