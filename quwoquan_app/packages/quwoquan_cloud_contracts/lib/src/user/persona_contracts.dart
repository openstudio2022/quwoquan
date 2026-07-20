import '../operation_request_payload.dart';

enum PersonaIsolationLevel {
  open('open'),
  semi('semi'),
  strict('strict');

  const PersonaIsolationLevel(this.wireValue);
  final String wireValue;

  static PersonaIsolationLevel fromWire(String? value) =>
      PersonaIsolationLevel.values.firstWhere(
        (item) => item.wireValue == value,
        orElse: () => PersonaIsolationLevel.open,
      );
}

/// Persona（分身/子账号）聚合命令的 pure contracts。
/// 真相源：contracts/metadata/user/persona/{service,fields}.yaml 与
/// user_profile/fields.yaml 的 persona 管理视图。
/// userHandle 由服务端系统分配，客户端不提交；激活切换为强一致排他写。

final class CreatePersonaCommand {
  CreatePersonaCommand({
    required String displayName,
    this.avatarUrl,
    this.isolationLevel,
    this.purposeHint,
  }) : displayName = _required(displayName, 'displayName');

  final String displayName;
  final String? avatarUrl;
  final String? isolationLevel;
  final String? purposeHint;
}

/// PATCH 语义：仅编码非 null 字段。
final class UpdatePersonaCommand {
  UpdatePersonaCommand({
    required String subAccountId,
    this.displayName,
    this.phone,
    this.email,
    this.avatarUrl,
    this.backgroundUrl,
    this.isolationLevel,
    this.purposeHint,
    this.applyScope,
    this.syncTargetIds,
    this.fieldsMask,
  }) : subAccountId = _required(subAccountId, 'subAccountId');

  final String subAccountId;
  final String? displayName;
  final String? phone;
  final String? email;
  final String? avatarUrl;
  final String? backgroundUrl;
  final String? isolationLevel;
  final String? purposeHint;
  final String? applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;
}

final class ApplyPersonaProfileSyncCommand {
  ApplyPersonaProfileSyncCommand({
    required String subAccountId,
    required String applyScope,
    this.syncTargetIds,
    this.fieldsMask,
  }) : subAccountId = _required(subAccountId, 'subAccountId'),
       applyScope = _required(applyScope, 'applyScope');

  final String subAccountId;
  final String applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;
}

final class RetirePersonaCommand {
  RetirePersonaCommand({required String subAccountId})
    : subAccountId = _required(subAccountId, 'subAccountId');

  final String subAccountId;
}

final class ActivatePersonaCommand {
  ActivatePersonaCommand({required String subAccountId})
    : subAccountId = _required(subAccountId, 'subAccountId');

  final String subAccountId;
}

/// 资料保存命令（PATCH /user/profile）。仅编码非 null 字段。
final class UpdateUserProfileCommand {
  UpdateUserProfileCommand({
    this.nickname,
    this.displayName,
    this.avatarAssetId,
    this.avatarUrl,
    this.backgroundAssetId,
    this.backgroundUrl,
    this.bio,
    this.gender,
    this.birthDate,
    this.regionTagRef,
    this.occupationTagRef,
    this.interestTagRefs,
    this.identityTags,
    this.profileVisibility,
    this.applyScope,
    this.syncTargetIds,
    this.fieldsMask,
  });

  final String? nickname;
  final String? displayName;
  final String? avatarAssetId;
  final String? avatarUrl;
  final String? backgroundAssetId;
  final String? backgroundUrl;
  final String? bio;
  final String? gender;
  final String? birthDate;
  final String? regionTagRef;
  final String? occupationTagRef;
  final List<String>? interestTagRefs;
  final List<String>? identityTags;
  final String? profileVisibility;
  final String? applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;
}

/// 分身管理列表项视图（owner 私有）。
final class PersonaManagementItem {
  const PersonaManagementItem({
    required this.subAccountId,
    required this.displayName,
    required this.isolationLevel,
    required this.isActive,
    required this.isPrimary,
    required this.status,
    required this.inheritsProfileFromOwner,
    required this.profileVisibility,
    required this.updatedAt,
    this.userHandle,
    this.phone,
    this.email,
    this.avatarUrl,
    this.backgroundUrl,
    this.bio,
    this.retiredAt,
    this.overriddenProfileFields = const <String>[],
    this.lastProfileSyncAt,
    this.lastProfileSyncSource,
    this.purposeHint,
    this.lastActivatedAt,
  });

  final String subAccountId;
  final String displayName;
  final String? userHandle;
  final String? phone;
  final String? email;
  final String? avatarUrl;
  final String? backgroundUrl;
  final String? bio;
  final String isolationLevel;
  final bool isActive;
  final bool isPrimary;
  final String status;
  final String? retiredAt;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final String? lastProfileSyncAt;
  final String? lastProfileSyncSource;
  final String profileVisibility;
  final String? purposeHint;
  final String updatedAt;
  final String? lastActivatedAt;
}

/// 激活分身上下文快照（激活切换命令回执）。
final class ActivePersonaContext {
  const ActivePersonaContext({
    required this.ownerUserId,
    required this.subAccountId,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.contextVersion,
    required this.personaSnapshotVersion,
    required this.explicitOverride,
    required this.switchedAt,
    this.sourceSurfaceId,
  });

  final String ownerUserId;
  final String subAccountId;
  final String isolationLevel;
  final String profileVisibility;
  final int contextVersion;
  final int personaSnapshotVersion;
  final String? sourceSurfaceId;
  final bool explicitOverride;
  final String switchedAt;
}

/// 退役命令回执：生命周期保护判定视图。
final class PersonaLifecycleGuard {
  const PersonaLifecycleGuard({
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
}

final class PersonaProfileSyncResult {
  const PersonaProfileSyncResult({
    required this.status,
    required this.appliedCount,
    required this.fieldsMask,
  });

  final String status;
  final int appliedCount;
  final List<String> fieldsMask;
}

/// 资料保存命令回执（服务端合成后的权威快照摘要）。
final class ProfileUpdateSnapshot {
  const ProfileUpdateSnapshot({
    required this.userId,
    required this.nickname,
    required this.nicknameCustomized,
    required this.profileVersion,
    this.accountState,
    this.avatarUrl,
    this.avatarAssetId,
    this.avatarVersion = 0,
    this.backgroundUrl,
    this.backgroundAssetId,
    this.bio,
    this.identityTags = const <String>[],
    this.gender,
    this.birthDate,
    this.region,
    this.regionTagRef,
    this.status,
    this.updatedAt,
  });

  final String userId;
  final String nickname;
  final bool nicknameCustomized;
  final int profileVersion;
  final String? accountState;
  final String? avatarUrl;
  final String? avatarAssetId;
  final int avatarVersion;
  final String? backgroundUrl;
  final String? backgroundAssetId;
  final String? bio;
  final List<String> identityTags;
  final String? gender;
  final String? birthDate;
  final String? region;
  final String? regionTagRef;
  final String? status;
  final String? updatedAt;
}

abstract interface class PersonaManagementCommandWriter {
  Future<PersonaManagementItem> createPersona(CreatePersonaCommand command);

  Future<PersonaManagementItem> updatePersona(UpdatePersonaCommand command);

  Future<PersonaProfileSyncResult> applyPersonaProfileSync(
    ApplyPersonaProfileSyncCommand command,
  );

  Future<PersonaLifecycleGuard> retirePersona(RetirePersonaCommand command);

  Future<ActivePersonaContext> activatePersona(ActivatePersonaCommand command);
}

abstract interface class ProfileCommandWriter {
  Future<ProfileUpdateSnapshot> updateUserProfile(
    UpdateUserProfileCommand command,
  );
}

CloudOperationRequestPayload encodeCreatePersonaCommand(
  CreatePersonaCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'displayName': command.displayName,
    if (command.avatarUrl != null) 'avatarUrl': command.avatarUrl,
    if (command.isolationLevel != null)
      'isolationLevel': command.isolationLevel,
    if (command.purposeHint != null) 'purposeHint': command.purposeHint,
  },
);

CloudOperationRequestPayload encodeUpdatePersonaCommand(
  UpdatePersonaCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'subAccountId': command.subAccountId},
  body: <String, Object?>{
    if (command.displayName != null) 'displayName': command.displayName,
    if (command.phone != null) 'phone': command.phone,
    if (command.email != null) 'email': command.email,
    if (command.avatarUrl != null) 'avatarUrl': command.avatarUrl,
    if (command.backgroundUrl != null) 'backgroundUrl': command.backgroundUrl,
    if (command.isolationLevel != null)
      'isolationLevel': command.isolationLevel,
    if (command.purposeHint != null) 'purposeHint': command.purposeHint,
    if (command.applyScope != null) 'applyScope': command.applyScope,
    if (command.syncTargetIds != null) 'syncTargetIds': command.syncTargetIds,
    if (command.fieldsMask != null) 'fieldsMask': command.fieldsMask,
  },
);

CloudOperationRequestPayload encodeApplyPersonaProfileSyncCommand(
  ApplyPersonaProfileSyncCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'subAccountId': command.subAccountId},
  body: <String, Object?>{
    'applyScope': command.applyScope,
    if (command.syncTargetIds != null) 'syncTargetIds': command.syncTargetIds,
    if (command.fieldsMask != null) 'fieldsMask': command.fieldsMask,
  },
);

CloudOperationRequestPayload encodeRetirePersonaCommand(
  RetirePersonaCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'subAccountId': command.subAccountId},
);

CloudOperationRequestPayload encodeActivatePersonaCommand(
  ActivatePersonaCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'subAccountId': command.subAccountId},
);

CloudOperationRequestPayload encodeUpdateUserProfileCommand(
  UpdateUserProfileCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    if (command.nickname != null) 'nickname': command.nickname,
    if (command.displayName != null) 'displayName': command.displayName,
    if (command.avatarAssetId != null) 'avatarAssetId': command.avatarAssetId,
    if (command.avatarUrl != null) 'avatarUrl': command.avatarUrl,
    if (command.backgroundAssetId != null)
      'backgroundAssetId': command.backgroundAssetId,
    if (command.backgroundUrl != null) 'backgroundUrl': command.backgroundUrl,
    if (command.bio != null) 'bio': command.bio,
    if (command.gender != null) 'gender': command.gender,
    if (command.birthDate != null) 'birthDate': command.birthDate,
    if (command.regionTagRef != null) 'regionTagRef': command.regionTagRef,
    if (command.occupationTagRef != null)
      'occupationTagRef': command.occupationTagRef,
    if (command.interestTagRefs != null)
      'interestTagRefs': command.interestTagRefs,
    if (command.identityTags != null) 'identityTags': command.identityTags,
    if (command.profileVisibility != null)
      'profileVisibility': command.profileVisibility,
    if (command.applyScope != null) 'applyScope': command.applyScope,
    if (command.syncTargetIds != null) 'syncTargetIds': command.syncTargetIds,
    if (command.fieldsMask != null) 'fieldsMask': command.fieldsMask,
  },
);

PersonaManagementItem decodePersonaManagementItem(Object? value) {
  final map = _object(value, 'PersonaManagementItem');
  return PersonaManagementItem(
    subAccountId: _string(map, 'subAccountId'),
    displayName: _stringOr(map, 'displayName', ''),
    userHandle: _optionalString(map, 'userHandle'),
    phone: _optionalString(map, 'phone'),
    email: _optionalString(map, 'email'),
    avatarUrl: _optionalString(map, 'avatarUrl'),
    backgroundUrl: _optionalString(map, 'backgroundUrl'),
    bio: _optionalString(map, 'bio'),
    isolationLevel: _stringOr(map, 'isolationLevel', 'open'),
    isActive: _boolOr(map, 'isActive', false),
    isPrimary: _boolOr(map, 'isPrimary', false),
    status: _stringOr(map, 'status', 'active'),
    retiredAt: _optionalString(map, 'retiredAt'),
    inheritsProfileFromOwner: _boolOr(map, 'inheritsProfileFromOwner', true),
    overriddenProfileFields: _stringList(map['overriddenProfileFields']),
    lastProfileSyncAt: _optionalString(map, 'lastProfileSyncAt'),
    lastProfileSyncSource: _optionalString(map, 'lastProfileSyncSource'),
    profileVisibility: _stringOr(map, 'profileVisibility', 'public'),
    purposeHint: _optionalString(map, 'purposeHint'),
    updatedAt: _stringOr(map, 'updatedAt', ''),
    lastActivatedAt: _optionalString(map, 'lastActivatedAt'),
  );
}

ActivePersonaContext decodeActivePersonaContext(Object? value) {
  final map = _object(value, 'ActivePersonaContext');
  return ActivePersonaContext(
    ownerUserId: _string(map, 'ownerUserId'),
    subAccountId: _string(map, 'subAccountId'),
    isolationLevel: _stringOr(map, 'isolationLevel', 'open'),
    profileVisibility: _stringOr(map, 'profileVisibility', 'public'),
    contextVersion: _intOr(map, 'contextVersion', 1),
    personaSnapshotVersion: _intOr(map, 'personaSnapshotVersion', 1),
    sourceSurfaceId: _optionalString(map, 'sourceSurfaceId'),
    explicitOverride: _boolOr(map, 'explicitOverride', false),
    switchedAt: _stringOr(map, 'switchedAt', ''),
  );
}

PersonaLifecycleGuard decodePersonaLifecycleGuard(Object? value) {
  final map = _object(value, 'PersonaLifecycleGuard');
  return PersonaLifecycleGuard(
    subAccountId: _string(map, 'subAccountId'),
    requestedAction: _stringOr(map, 'requestedAction', ''),
    allowed: _boolOr(map, 'allowed', false),
    reason: _stringOr(map, 'reason', ''),
    requiresSuccessor: _boolOr(map, 'requiresSuccessor', false),
  );
}

PersonaProfileSyncResult decodePersonaProfileSyncResult(Object? value) {
  final map = _object(value, 'PersonaProfileSyncResult');
  return PersonaProfileSyncResult(
    status: _stringOr(map, 'status', 'ok'),
    appliedCount: _intOr(map, 'appliedCount', 0),
    fieldsMask: _stringList(map['fieldsMask']),
  );
}

ProfileUpdateSnapshot decodeProfileUpdateSnapshot(Object? value) {
  final map = _object(value, 'ProfileUpdateSnapshot');
  return ProfileUpdateSnapshot(
    userId: _string(map, 'userId'),
    nickname: _stringOr(map, 'nickname', ''),
    nicknameCustomized: _boolOr(map, 'nicknameCustomized', false),
    profileVersion: _intOr(map, 'profileVersion', 1),
    accountState: _optionalString(map, 'accountState'),
    avatarUrl: _optionalString(map, 'avatarUrl'),
    avatarAssetId: _optionalString(map, 'avatarAssetId'),
    avatarVersion: _intOr(map, 'avatarVersion', 0),
    backgroundUrl: _optionalString(map, 'backgroundUrl'),
    backgroundAssetId: _optionalString(map, 'backgroundAssetId'),
    bio: _optionalString(map, 'bio'),
    identityTags: _stringList(map['identityTags']),
    gender: _optionalString(map, 'gender'),
    birthDate: _optionalString(map, 'birthDate'),
    region: _optionalString(map, 'region'),
    regionTagRef: _optionalString(map, 'regionTagRef'),
    status: _optionalString(map, 'status'),
    updatedAt: _optionalString(map, 'updatedAt'),
  );
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String _stringOr(Map<String, Object?> map, String key, String fallback) {
  final value = map[key];
  if (value is String && value.trim().isNotEmpty) return value.trim();
  return fallback;
}

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is String && value.trim().isNotEmpty) return value.trim();
  return null;
}

List<String> _stringList(Object? value) {
  if (value is! List) return const <String>[];
  return List<String>.unmodifiable(
    value
        .whereType<String>()
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty),
  );
}

int _intOr(Map<String, Object?> map, String key, int fallback) {
  final value = map[key];
  if (value is int) return value;
  if (value is num) return value.toInt();
  return fallback;
}

bool _boolOr(Map<String, Object?> map, String key, bool fallback) {
  final value = map[key];
  if (value is bool) return value;
  return fallback;
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}
