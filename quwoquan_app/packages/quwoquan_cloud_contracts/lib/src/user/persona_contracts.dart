import '../operation_request_payload.dart';
part '../generated/requests/user/persona_contracts.requests.g.dart';

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

/// 分身管理列表项视图（owner 私有）。
final class PersonaManagementItem {
  const PersonaManagementItem({
    required this.personaId,
    required this.displayName,
    required this.isolationLevel,
    required this.isActive,
    required this.isPrimary,
    required this.status,
    required this.inheritsProfileFromOwner,
    required this.profileVisibility,
    required this.updatedAt,
    this.userHandle,
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

  final String personaId;
  final String displayName;
  final String? userHandle;
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
    required this.personaId,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.contextVersion,
    required this.personaSnapshotVersion,
    required this.explicitOverride,
    required this.switchedAt,
    this.sourceSurfaceId,
  });

  final String ownerUserId;
  final String personaId;
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

PersonaManagementItem decodePersonaManagementItem(Object? value) {
  final map = _object(value, 'PersonaManagementItem');
  return PersonaManagementItem(
    personaId: _string(map, 'personaId'),
    displayName: _stringOr(map, 'displayName', ''),
    userHandle: _optionalString(map, 'userHandle'),
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
    personaId: _string(map, 'personaId'),
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
    personaId: _string(map, 'personaId'),
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
