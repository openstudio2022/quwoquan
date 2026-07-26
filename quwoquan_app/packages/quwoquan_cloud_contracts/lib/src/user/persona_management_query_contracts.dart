import '../operation_request_payload.dart';
import 'user_contract_codec.dart';

abstract interface class PersonaManagementQueryFacet {
  Future<ListPersonasResult> listPersonas(ListPersonasQuery query);

  Future<PersonaManagementSummaryProjection> getPersonaManagementSummary(
    GetPersonaManagementSummaryQuery query,
  );

  Future<ActivePersonaContextProjection> getActivePersonaContext(
    GetActivePersonaContextQuery query,
  );

  Future<PersonaLifecycleGuardProjection> getPersonaLifecycleGuard(
    GetPersonaLifecycleGuardQuery query,
  );
}

final class ListPersonasQuery {
  const ListPersonasQuery();

  Map<String, Object?> toJson() => const <String, Object?>{};
}

CloudOperationRequestPayload encodeListPersonasQuery(ListPersonasQuery query) =>
    const CloudOperationRequestPayload();

final class PersonaManagementItemProjection {
  const PersonaManagementItemProjection({
    required this.subAccountId,
    required this.displayName,
    required this.userHandle,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.isPrimary,
    required this.isActive,
    required this.status,
    required this.hasPublishedContent,
    required this.inheritsProfileFromOwner,
    required this.overriddenProfileFields,
    required this.subjectType,
    this.phone,
    this.email,
    this.avatarUrl,
    this.avatarVersion = 0,
    this.backgroundUrl,
    this.bio,
    this.retiredAt,
    this.lastProfileSyncAt,
    this.lastProfileSyncSource,
    this.lastActivatedAt,
    this.updatedAt,
  });

  final String subAccountId;
  final String displayName;
  final String userHandle;
  final String? phone;
  final String? email;
  final String? avatarUrl;
  final int avatarVersion;
  final String? backgroundUrl;
  final String? bio;
  final String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  final bool isActive;
  final String status;
  final DateTime? retiredAt;
  final bool hasPublishedContent;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final String subjectType;
  final DateTime? lastProfileSyncAt;
  final String? lastProfileSyncSource;
  final DateTime? lastActivatedAt;
  final DateTime? updatedAt;

  static PersonaManagementItemProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'PersonaManagementItemProjection',
    );
    return PersonaManagementItemProjection(
      subAccountId: UserContractCodec.requiredText(source, 'subAccountId'),
      displayName: UserContractCodec.requiredText(source, 'displayName'),
      userHandle: UserContractCodec.requiredText(source, 'userHandle'),
      phone: UserContractCodec.optionalText(source['phone']),
      email: UserContractCodec.optionalText(source['email']),
      avatarUrl: UserContractCodec.optionalText(source['avatarUrl']),
      avatarVersion: UserContractCodec.integerOr(source, 'avatarVersion', 0),
      backgroundUrl: UserContractCodec.optionalText(source['backgroundUrl']),
      bio: UserContractCodec.optionalText(source['bio']),
      isolationLevel: UserContractCodec.textOr(
        source,
        'isolationLevel',
        'open',
      ),
      profileVisibility: UserContractCodec.textOr(
        source,
        'profileVisibility',
        'public',
      ),
      isPrimary: UserContractCodec.booleanOr(source, 'isPrimary', false),
      isActive: UserContractCodec.booleanOr(source, 'isActive', false),
      status: UserContractCodec.textOr(source, 'status', 'active'),
      retiredAt: UserContractCodec.optionalTimestamp(source, 'retiredAt'),
      hasPublishedContent: UserContractCodec.booleanOr(
        source,
        'hasPublishedContent',
        false,
      ),
      inheritsProfileFromOwner: UserContractCodec.booleanOr(
        source,
        'inheritsProfileFromOwner',
        false,
      ),
      overriddenProfileFields: UserContractCodec.stringList(
        source['overriddenProfileFields'],
        'overriddenProfileFields',
      ),
      lastProfileSyncAt: UserContractCodec.optionalTimestamp(
        source,
        'lastProfileSyncAt',
      ),
      lastProfileSyncSource: UserContractCodec.optionalText(
        source['lastProfileSyncSource'],
      ),
      lastActivatedAt: UserContractCodec.optionalTimestamp(
        source,
        'lastActivatedAt',
      ),
      subjectType: UserContractCodec.textOr(source, 'subjectType', 'persona'),
      updatedAt: UserContractCodec.optionalTimestamp(source, 'updatedAt'),
    );
  }
}

final class ListPersonasResult {
  const ListPersonasResult({required this.items});

  final List<PersonaManagementItemProjection> items;

  static ListPersonasResult fromJson(Object? value) {
    final source = UserContractCodec.object(value, 'ListPersonasResult');
    return ListPersonasResult(
      items: List<PersonaManagementItemProjection>.unmodifiable(
        UserContractCodec.objectList(
          source['items'],
          'ListPersonasResult.items',
        ).map(PersonaManagementItemProjection.fromJson),
      ),
    );
  }
}

ListPersonasResult decodeListPersonasResult(Object? value) {
  return ListPersonasResult.fromJson(value);
}

final class GetPersonaManagementSummaryQuery {
  const GetPersonaManagementSummaryQuery();

  Map<String, Object?> toJson() => const <String, Object?>{};
}

CloudOperationRequestPayload encodeGetPersonaManagementSummaryQuery(
  GetPersonaManagementSummaryQuery query,
) => const CloudOperationRequestPayload();

final class PersonaManagementQuotaProjection {
  const PersonaManagementQuotaProjection({
    required this.ownerUserId,
    required this.totalCount,
    required this.quotaLimit,
    required this.remainingCount,
    this.activeProfileSubjectId,
    this.primaryProfileSubjectId,
  });

  final String ownerUserId;
  final int totalCount;
  final int quotaLimit;
  final int remainingCount;
  final String? activeProfileSubjectId;
  final String? primaryProfileSubjectId;

  static PersonaManagementQuotaProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'PersonaManagementQuotaProjection',
    );
    return PersonaManagementQuotaProjection(
      ownerUserId: UserContractCodec.requiredText(source, 'ownerUserId'),
      totalCount: UserContractCodec.integerOr(source, 'totalCount', 0),
      quotaLimit: UserContractCodec.integerOr(source, 'quotaLimit', 0),
      remainingCount: UserContractCodec.integerOr(source, 'remainingCount', 0),
      activeProfileSubjectId: UserContractCodec.optionalText(
        source['activeProfileSubjectId'],
      ),
      primaryProfileSubjectId: UserContractCodec.optionalText(
        source['primaryProfileSubjectId'],
      ),
    );
  }
}

final class ActivePersonaContextProjection {
  const ActivePersonaContextProjection({
    required this.ownerUserId,
    required this.subAccountId,
    required this.subjectType,
    required this.displayName,
    required this.avatarUrl,
    required this.avatarVersion,
    required this.isPrimary,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.contextVersion,
    required this.personaSnapshotVersion,
    required this.sourceSurfaceId,
    required this.explicitOverride,
    this.switchedAt,
  });

  final String ownerUserId;
  final String subAccountId;
  final String subjectType;
  final String displayName;
  final String avatarUrl;
  final int avatarVersion;
  final bool isPrimary;
  final String isolationLevel;
  final String profileVisibility;
  final int contextVersion;
  final int personaSnapshotVersion;
  final String sourceSurfaceId;
  final bool explicitOverride;
  final DateTime? switchedAt;

  static ActivePersonaContextProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'ActivePersonaContextProjection',
    );
    return ActivePersonaContextProjection(
      ownerUserId: UserContractCodec.requiredText(source, 'ownerUserId'),
      subAccountId: UserContractCodec.requiredText(source, 'subAccountId'),
      subjectType: UserContractCodec.textOr(source, 'subjectType', 'persona'),
      displayName: UserContractCodec.textOr(source, 'displayName', ''),
      avatarUrl: UserContractCodec.textOr(source, 'avatarUrl', ''),
      avatarVersion: UserContractCodec.integerOr(source, 'avatarVersion', 0),
      isPrimary: UserContractCodec.booleanOr(source, 'isPrimary', false),
      isolationLevel: UserContractCodec.textOr(
        source,
        'isolationLevel',
        'open',
      ),
      profileVisibility: UserContractCodec.textOr(
        source,
        'profileVisibility',
        'public',
      ),
      contextVersion: UserContractCodec.integerOr(source, 'contextVersion', 1),
      personaSnapshotVersion: UserContractCodec.integerOr(
        source,
        'personaSnapshotVersion',
        1,
      ),
      sourceSurfaceId: UserContractCodec.textOr(source, 'sourceSurfaceId', ''),
      explicitOverride: UserContractCodec.booleanOr(
        source,
        'explicitOverride',
        false,
      ),
      switchedAt: UserContractCodec.optionalTimestamp(source, 'switchedAt'),
    );
  }
}

final class PersonaManagementSummaryProjection {
  const PersonaManagementSummaryProjection({
    required this.items,
    required this.quota,
    required this.activeContext,
  });

  final List<PersonaManagementItemProjection> items;
  final PersonaManagementQuotaProjection quota;
  final ActivePersonaContextProjection activeContext;

  static PersonaManagementSummaryProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'PersonaManagementSummaryProjection',
    );
    return PersonaManagementSummaryProjection(
      items: List<PersonaManagementItemProjection>.unmodifiable(
        UserContractCodec.objectList(
          source['items'],
          'PersonaManagementSummaryProjection.items',
        ).map(PersonaManagementItemProjection.fromJson),
      ),
      quota: PersonaManagementQuotaProjection.fromJson(source['quota']),
      activeContext: ActivePersonaContextProjection.fromJson(
        source['activeContext'],
      ),
    );
  }
}

PersonaManagementSummaryProjection decodePersonaManagementSummaryProjection(
  Object? value,
) {
  return PersonaManagementSummaryProjection.fromJson(value);
}

final class GetActivePersonaContextQuery {
  const GetActivePersonaContextQuery();

  Map<String, Object?> toJson() => const <String, Object?>{};
}

CloudOperationRequestPayload encodeGetActivePersonaContextQuery(
  GetActivePersonaContextQuery _,
) => const CloudOperationRequestPayload();

ActivePersonaContextProjection decodeActivePersonaContextProjection(
  Object? value,
) {
  return ActivePersonaContextProjection.fromJson(value);
}

final class GetPersonaLifecycleGuardQuery {
  const GetPersonaLifecycleGuardQuery({required this.subAccountId});

  final String subAccountId;

  Map<String, Object?> toJson() => <String, Object?>{
    'subAccountId': subAccountId,
  };
}

CloudOperationRequestPayload encodeGetPersonaLifecycleGuardQuery(
  GetPersonaLifecycleGuardQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'subAccountId': query.subAccountId},
);

final class PersonaLifecycleGuardProjection {
  const PersonaLifecycleGuardProjection({
    required this.subAccountId,
    required this.requestedAction,
    required this.allowed,
    required this.reason,
    required this.requiresSuccessor,
  });

  final String subAccountId;
  final String requestedAction;
  final bool allowed;
  final String reason;
  final bool requiresSuccessor;

  static PersonaLifecycleGuardProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'PersonaLifecycleGuardProjection',
    );
    return PersonaLifecycleGuardProjection(
      subAccountId: UserContractCodec.requiredText(source, 'subAccountId'),
      requestedAction: UserContractCodec.textOr(
        source,
        'requestedAction',
        'retire',
      ),
      allowed: UserContractCodec.booleanOr(source, 'allowed', false),
      reason: UserContractCodec.textOr(source, 'reason', ''),
      requiresSuccessor: UserContractCodec.booleanOr(
        source,
        'requiresSuccessor',
        false,
      ),
    );
  }
}

PersonaLifecycleGuardProjection decodePersonaLifecycleGuardProjection(
  Object? value,
) {
  return PersonaLifecycleGuardProjection.fromJson(value);
}
