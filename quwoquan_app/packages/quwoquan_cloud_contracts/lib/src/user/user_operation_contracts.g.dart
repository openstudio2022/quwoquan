// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 26c2e545293cccf457d21c4709e21c53e088e6c7cb499a6d7e1e82f9a23fe024

library;

import '../operation_request_payload.dart';
import "../generated/shared_operation_enums.g.dart";
import "../generated/shared_operation_types.g.dart";

export "../generated/shared_operation_enums.g.dart";
export "../generated/shared_operation_types.g.dart";

part '../generated/requests/user/user_operation_contracts.g.requests.g.dart';

enum AccountState {
  anonymous("anonymous"),
  active("active"),
  suspended("suspended"),
  closed("closed");

  const AccountState(this.wireName);

  final String wireName;

  static AccountState fromWire(Object? value, String path) {
    return switch (value) {
      "anonymous" => AccountState.anonymous,
      "active" => AccountState.active,
      "suspended" => AccountState.suspended,
      "closed" => AccountState.closed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum AppearanceApplyScope {
  allAccounts("all_accounts"),
  currentPersona("current_persona"),
  inheritOwnerDefault("inherit_owner_default");

  const AppearanceApplyScope(this.wireName);

  final String wireName;

  static AppearanceApplyScope fromWire(Object? value, String path) {
    return switch (value) {
      "all_accounts" => AppearanceApplyScope.allAccounts,
      "current_persona" => AppearanceApplyScope.currentPersona,
      "inherit_owner_default" => AppearanceApplyScope.inheritOwnerDefault,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum AppearanceSource {
  ownerDefault("owner_default"),
  subOverride("sub_override"),
  systemDefault("system_default");

  const AppearanceSource(this.wireName);

  final String wireName;

  static AppearanceSource fromWire(Object? value, String path) {
    return switch (value) {
      "owner_default" => AppearanceSource.ownerDefault,
      "sub_override" => AppearanceSource.subOverride,
      "system_default" => AppearanceSource.systemDefault,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CredentialType {
  anonymousDevice("anonymous_device"),
  phone("phone"),
  carrierPhone("carrier_phone"),
  federatedSlotA("federated_slot_a"),
  federatedSlotB("federated_slot_b"),
  federatedSlotC("federated_slot_c"),
  apple("apple"),
  passkey("passkey");

  const CredentialType(this.wireName);

  final String wireName;

  static CredentialType fromWire(Object? value, String path) {
    return switch (value) {
      "anonymous_device" => CredentialType.anonymousDevice,
      "phone" => CredentialType.phone,
      "carrier_phone" => CredentialType.carrierPhone,
      "federated_slot_a" => CredentialType.federatedSlotA,
      "federated_slot_b" => CredentialType.federatedSlotB,
      "federated_slot_c" => CredentialType.federatedSlotC,
      "apple" => CredentialType.apple,
      "passkey" => CredentialType.passkey,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum DevicePushEndpointKind {
  apnsVoip("apns_voip"),
  fcm("fcm");

  const DevicePushEndpointKind(this.wireName);

  final String wireName;

  static DevicePushEndpointKind fromWire(Object? value, String path) {
    return switch (value) {
      "apns_voip" => DevicePushEndpointKind.apnsVoip,
      "fcm" => DevicePushEndpointKind.fcm,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum DeviceRegistrationStatus {
  active("active"),
  revoked("revoked"),
  stale("stale");

  const DeviceRegistrationStatus(this.wireName);

  final String wireName;

  static DeviceRegistrationStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => DeviceRegistrationStatus.active,
      "revoked" => DeviceRegistrationStatus.revoked,
      "stale" => DeviceRegistrationStatus.stale,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum DiscoveryStatus {
  pending("pending"),
  processing("processing"),
  completed("completed"),
  dismissed("dismissed");

  const DiscoveryStatus(this.wireName);

  final String wireName;

  static DiscoveryStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => DiscoveryStatus.pending,
      "processing" => DiscoveryStatus.processing,
      "completed" => DiscoveryStatus.completed,
      "dismissed" => DiscoveryStatus.dismissed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum FederatedLoginStatus {
  authenticated("authenticated"),
  phonebindingrequired("phoneBindingRequired");

  const FederatedLoginStatus(this.wireName);

  final String wireName;

  static FederatedLoginStatus fromWire(Object? value, String path) {
    return switch (value) {
      "authenticated" => FederatedLoginStatus.authenticated,
      "phoneBindingRequired" => FederatedLoginStatus.phonebindingrequired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum FeedPreference {
  recommend("recommend"),
  chronological("chronological");

  const FeedPreference(this.wireName);

  final String wireName;

  static FeedPreference fromWire(Object? value, String path) {
    return switch (value) {
      "recommend" => FeedPreference.recommend,
      "chronological" => FeedPreference.chronological,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum FollowSubjectKind {
  persona("persona"),
  homepage("homepage"),
  circle("circle"),
  location("location");

  const FollowSubjectKind(this.wireName);

  final String wireName;

  static FollowSubjectKind fromWire(Object? value, String path) {
    return switch (value) {
      "persona" => FollowSubjectKind.persona,
      "homepage" => FollowSubjectKind.homepage,
      "circle" => FollowSubjectKind.circle,
      "location" => FollowSubjectKind.location,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum FontSizePreset {
  xs("xs"),
  sm("sm"),
  md("md"),
  lg("lg"),
  xl("xl");

  const FontSizePreset(this.wireName);

  final String wireName;

  static FontSizePreset fromWire(Object? value, String path) {
    return switch (value) {
      "xs" => FontSizePreset.xs,
      "sm" => FontSizePreset.sm,
      "md" => FontSizePreset.md,
      "lg" => FontSizePreset.lg,
      "xl" => FontSizePreset.xl,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum Gender {
  male("male"),
  female("female"),
  other("other"),
  unspecified("unspecified");

  const Gender(this.wireName);

  final String wireName;

  static Gender fromWire(Object? value, String path) {
    return switch (value) {
      "male" => Gender.male,
      "female" => Gender.female,
      "other" => Gender.other,
      "unspecified" => Gender.unspecified,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GreetingRequestSource {
  profile("profile"),
  recommendation("recommendation"),
  groupMember("group_member"),
  invite("invite");

  const GreetingRequestSource(this.wireName);

  final String wireName;

  static GreetingRequestSource fromWire(Object? value, String path) {
    return switch (value) {
      "profile" => GreetingRequestSource.profile,
      "recommendation" => GreetingRequestSource.recommendation,
      "group_member" => GreetingRequestSource.groupMember,
      "invite" => GreetingRequestSource.invite,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GreetingRequestStatus {
  pending("pending"),
  replied("replied"),
  ignored("ignored"),
  blocked("blocked"),
  cancelled("cancelled"),
  expired("expired");

  const GreetingRequestStatus(this.wireName);

  final String wireName;

  static GreetingRequestStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => GreetingRequestStatus.pending,
      "replied" => GreetingRequestStatus.replied,
      "ignored" => GreetingRequestStatus.ignored,
      "blocked" => GreetingRequestStatus.blocked,
      "cancelled" => GreetingRequestStatus.cancelled,
      "expired" => GreetingRequestStatus.expired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IsolationLevel {
  open("open"),
  semi("semi"),
  strict("strict");

  const IsolationLevel(this.wireName);

  final String wireName;

  static IsolationLevel fromWire(Object? value, String path) {
    return switch (value) {
      "open" => IsolationLevel.open,
      "semi" => IsolationLevel.semi,
      "strict" => IsolationLevel.strict,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum OtpClientPlatform {
  ios("ios"),
  android("android"),
  web("web"),
  acceptance("acceptance");

  const OtpClientPlatform(this.wireName);

  final String wireName;

  static OtpClientPlatform fromWire(Object? value, String path) {
    return switch (value) {
      "ios" => OtpClientPlatform.ios,
      "android" => OtpClientPlatform.android,
      "web" => OtpClientPlatform.web,
      "acceptance" => OtpClientPlatform.acceptance,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum OtpDeliveryAvailability {
  ready("ready"),
  temporarilyUnavailable("temporarily_unavailable");

  const OtpDeliveryAvailability(this.wireName);

  final String wireName;

  static OtpDeliveryAvailability fromWire(Object? value, String path) {
    return switch (value) {
      "ready" => OtpDeliveryAvailability.ready,
      "temporarily_unavailable" => OtpDeliveryAvailability.temporarilyUnavailable,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum OtpDeliveryStatus {
  queued("queued"),
  sentUnconfirmed("sent_unconfirmed"),
  delivered("delivered"),
  failed("failed");

  const OtpDeliveryStatus(this.wireName);

  final String wireName;

  static OtpDeliveryStatus fromWire(Object? value, String path) {
    return switch (value) {
      "queued" => OtpDeliveryStatus.queued,
      "sent_unconfirmed" => OtpDeliveryStatus.sentUnconfirmed,
      "delivered" => OtpDeliveryStatus.delivered,
      "failed" => OtpDeliveryStatus.failed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum PersonaLifecycleAction {
  retire("retire");

  const PersonaLifecycleAction(this.wireName);

  final String wireName;

  static PersonaLifecycleAction fromWire(Object? value, String path) {
    return switch (value) {
      "retire" => PersonaLifecycleAction.retire,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum PersonaLifecycleGuardReason {
  allowed("allowed"),
  blockedPrimaryPersona("blocked_primary_persona"),
  blockedLastPersona("blocked_last_persona"),
  blockedActivePersona("blocked_active_persona"),
  blockedRetiredPersona("blocked_retired_persona"),
  quotaReached("quota_reached");

  const PersonaLifecycleGuardReason(this.wireName);

  final String wireName;

  static PersonaLifecycleGuardReason fromWire(Object? value, String path) {
    return switch (value) {
      "allowed" => PersonaLifecycleGuardReason.allowed,
      "blocked_primary_persona" => PersonaLifecycleGuardReason.blockedPrimaryPersona,
      "blocked_last_persona" => PersonaLifecycleGuardReason.blockedLastPersona,
      "blocked_active_persona" => PersonaLifecycleGuardReason.blockedActivePersona,
      "blocked_retired_persona" => PersonaLifecycleGuardReason.blockedRetiredPersona,
      "quota_reached" => PersonaLifecycleGuardReason.quotaReached,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum PersonaStatus {
  active("active"),
  inactive("inactive"),
  retired("retired");

  const PersonaStatus(this.wireName);

  final String wireName;

  static PersonaStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => PersonaStatus.active,
      "inactive" => PersonaStatus.inactive,
      "retired" => PersonaStatus.retired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ProfileOwnerKind {
  account("account"),
  persona("persona"),
  creator("creator");

  const ProfileOwnerKind(this.wireName);

  final String wireName;

  static ProfileOwnerKind fromWire(Object? value, String path) {
    return switch (value) {
      "account" => ProfileOwnerKind.account,
      "persona" => ProfileOwnerKind.persona,
      "creator" => ProfileOwnerKind.creator,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ProfileVisibility {
  public("public"),
  friends("friends"),
  privateProfile("private");

  const ProfileVisibility(this.wireName);

  final String wireName;

  static ProfileVisibility fromWire(Object? value, String path) {
    return switch (value) {
      "public" => ProfileVisibility.public,
      "friends" => ProfileVisibility.friends,
      "private" => ProfileVisibility.privateProfile,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ProposalSource {
  persona("persona"),
  assistant("assistant"),
  external("external");

  const ProposalSource(this.wireName);

  final String wireName;

  static ProposalSource fromWire(Object? value, String path) {
    return switch (value) {
      "persona" => ProposalSource.persona,
      "assistant" => ProposalSource.assistant,
      "external" => ProposalSource.external,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ProposalStatus {
  pending("pending"),
  confirmed("confirmed"),
  applying("applying"),
  applied("applied"),
  rollingBack("rolling_back"),
  rolledBack("rolled_back"),
  rejected("rejected"),
  expired("expired");

  const ProposalStatus(this.wireName);

  final String wireName;

  static ProposalStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => ProposalStatus.pending,
      "confirmed" => ProposalStatus.confirmed,
      "applying" => ProposalStatus.applying,
      "applied" => ProposalStatus.applied,
      "rolling_back" => ProposalStatus.rollingBack,
      "rolled_back" => ProposalStatus.rolledBack,
      "rejected" => ProposalStatus.rejected,
      "expired" => ProposalStatus.expired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum SubjectFollowState {
  following("following"),
  unfollowed("unfollowed");

  const SubjectFollowState(this.wireName);

  final String wireName;

  static SubjectFollowState fromWire(Object? value, String path) {
    return switch (value) {
      "following" => SubjectFollowState.following,
      "unfollowed" => SubjectFollowState.unfollowed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum SubjectFollowTargetKind {
  homepage("homepage"),
  circle("circle"),
  location("location");

  const SubjectFollowTargetKind(this.wireName);

  final String wireName;

  static SubjectFollowTargetKind fromWire(Object? value, String path) {
    return switch (value) {
      "homepage" => SubjectFollowTargetKind.homepage,
      "circle" => SubjectFollowTargetKind.circle,
      "location" => SubjectFollowTargetKind.location,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ThemeModeSetting {
  system("system"),
  light("light"),
  dark("dark");

  const ThemeModeSetting(this.wireName);

  final String wireName;

  static ThemeModeSetting fromWire(Object? value, String path) {
    return switch (value) {
      "system" => ThemeModeSetting.system,
      "light" => ThemeModeSetting.light,
      "dark" => ThemeModeSetting.dark,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum UserSyncPatchKind {
  userAvatarUpdated("user_avatar_updated"),
  conversationAvatarUpdated("conversation_avatar_updated");

  const UserSyncPatchKind(this.wireName);

  final String wireName;

  static UserSyncPatchKind fromWire(Object? value, String path) {
    return switch (value) {
      "user_avatar_updated" => UserSyncPatchKind.userAvatarUpdated,
      "conversation_avatar_updated" => UserSyncPatchKind.conversationAvatarUpdated,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class AccountHintSnapshot {
  const AccountHintSnapshot({
    required this.displayName,
    required this.nicknameCustomized,
    required this.avatarUrl,
    required this.avatarAssetId,
    required this.maskedPhone,
    required this.identityOrigin,
  });

  final String displayName;
  final bool nicknameCustomized;
  final String avatarUrl;
  final String avatarAssetId;
  final String maskedPhone;
  final String identityOrigin;

  factory AccountHintSnapshot.fromWire(Map<String, Object?> map, [String path = "AccountHintSnapshot"]) {
    _rejectUnknownFields(map, const <String>{"displayName", "nicknameCustomized", "avatarUrl", "avatarAssetId", "maskedPhone", "identityOrigin"}, path);
    return AccountHintSnapshot(
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      nicknameCustomized: _requiredBool(map["nicknameCustomized"], '$path.nicknameCustomized'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      avatarAssetId: _requiredString(map["avatarAssetId"], '$path.avatarAssetId'),
      maskedPhone: _requiredString(map["maskedPhone"], '$path.maskedPhone'),
      identityOrigin: _requiredString(map["identityOrigin"], '$path.identityOrigin'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "displayName": displayName,
    "nicknameCustomized": nicknameCustomized,
    "avatarUrl": avatarUrl,
    "avatarAssetId": avatarAssetId,
    "maskedPhone": maskedPhone,
    "identityOrigin": identityOrigin,
  };
}

final class ActivePersonaContextView {
  const ActivePersonaContextView({
    required this.ownerUserId,
    required this.personaId,
    required this.subjectType,
    required this.displayName,
    this.avatarUrl,
    required this.avatarVersion,
    required this.isPrimary,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.contextVersion,
    required this.personaSnapshotVersion,
    this.sourceSurfaceId,
    required this.explicitOverride,
    required this.switchedAt,
  });

  final String ownerUserId;
  final String personaId;
  final ProfileOwnerKind subjectType;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final bool isPrimary;
  final IsolationLevel isolationLevel;
  final ProfileVisibility profileVisibility;
  final int contextVersion;
  final int personaSnapshotVersion;
  final String? sourceSurfaceId;
  final bool explicitOverride;
  final DateTime switchedAt;

  factory ActivePersonaContextView.fromWire(Map<String, Object?> map, [String path = "ActivePersonaContextView"]) {
    _rejectUnknownFields(map, const <String>{"ownerUserId", "personaId", "subjectType", "displayName", "avatarUrl", "avatarVersion", "isPrimary", "isolationLevel", "profileVisibility", "contextVersion", "personaSnapshotVersion", "sourceSurfaceId", "explicitOverride", "switchedAt"}, path);
    return ActivePersonaContextView(
      ownerUserId: _requiredString(map["ownerUserId"], '$path.ownerUserId'),
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      subjectType: ProfileOwnerKind.fromWire(map["subjectType"], '$path.subjectType'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      avatarVersion: _requiredInt(map["avatarVersion"], '$path.avatarVersion'),
      isPrimary: _requiredBool(map["isPrimary"], '$path.isPrimary'),
      isolationLevel: IsolationLevel.fromWire(map["isolationLevel"], '$path.isolationLevel'),
      profileVisibility: ProfileVisibility.fromWire(map["profileVisibility"], '$path.profileVisibility'),
      contextVersion: _requiredInt(map["contextVersion"], '$path.contextVersion'),
      personaSnapshotVersion: _requiredInt(map["personaSnapshotVersion"], '$path.personaSnapshotVersion'),
      sourceSurfaceId: map["sourceSurfaceId"] == null ? null : _requiredString(map["sourceSurfaceId"], '$path.sourceSurfaceId'),
      explicitOverride: _requiredBool(map["explicitOverride"], '$path.explicitOverride'),
      switchedAt: _requiredTimestamp(map["switchedAt"], '$path.switchedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "ownerUserId": ownerUserId,
    "personaId": personaId,
    "subjectType": subjectType.wireName,
    "displayName": displayName,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    "avatarVersion": avatarVersion,
    "isPrimary": isPrimary,
    "isolationLevel": isolationLevel.wireName,
    "profileVisibility": profileVisibility.wireName,
    "contextVersion": contextVersion,
    "personaSnapshotVersion": personaSnapshotVersion,
    if (sourceSurfaceId != null) "sourceSurfaceId": sourceSurfaceId!,
    "explicitOverride": explicitOverride,
    "switchedAt": switchedAt.toUtc().toIso8601String(),
  };
}

final class ActivePersonaEnvelope {
  const ActivePersonaEnvelope({
    required this.personaId,
  });

  final String personaId;

  factory ActivePersonaEnvelope.fromWire(Map<String, Object?> map, [String path = "ActivePersonaEnvelope"]) {
    _rejectUnknownFields(map, const <String>{"personaId"}, path);
    return ActivePersonaEnvelope(
      personaId: _requiredNonBlankString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
  };
}

final class AlipayAuthorizationGrant {
  const AlipayAuthorizationGrant({
    required this.authorizationPayload,
    required this.expiresAt,
  });

  final String authorizationPayload;
  final DateTime expiresAt;

  factory AlipayAuthorizationGrant.fromWire(Map<String, Object?> map, [String path = "AlipayAuthorizationGrant"]) {
    _rejectUnknownFields(map, const <String>{"authorizationPayload", "expiresAt"}, path);
    return AlipayAuthorizationGrant(
      authorizationPayload: _requiredNonBlankString(map["authorizationPayload"], '$path.authorizationPayload'),
      expiresAt: _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "authorizationPayload": authorizationPayload,
    "expiresAt": expiresAt.toUtc().toIso8601String(),
  };
}

final class AppearanceSettingsView {
  const AppearanceSettingsView({
    required this.themeMode,
    required this.fontSizePreset,
    required this.source,
    required this.ownerDefaultThemeMode,
    required this.ownerDefaultFontSizePreset,
    required this.hasPersonaOverride,
    required this.version,
    required this.updatedAt,
  });

  final ThemeModeSetting themeMode;
  final FontSizePreset fontSizePreset;
  final AppearanceSource source;
  final ThemeModeSetting ownerDefaultThemeMode;
  final FontSizePreset ownerDefaultFontSizePreset;
  final bool hasPersonaOverride;
  final int version;
  final DateTime updatedAt;

  factory AppearanceSettingsView.fromWire(Map<String, Object?> map, [String path = "AppearanceSettingsView"]) {
    _rejectUnknownFields(map, const <String>{"themeMode", "fontSizePreset", "source", "ownerDefaultThemeMode", "ownerDefaultFontSizePreset", "hasPersonaOverride", "version", "updatedAt"}, path);
    return AppearanceSettingsView(
      themeMode: ThemeModeSetting.fromWire(map["themeMode"], '$path.themeMode'),
      fontSizePreset: FontSizePreset.fromWire(map["fontSizePreset"], '$path.fontSizePreset'),
      source: AppearanceSource.fromWire(map["source"], '$path.source'),
      ownerDefaultThemeMode: ThemeModeSetting.fromWire(map["ownerDefaultThemeMode"], '$path.ownerDefaultThemeMode'),
      ownerDefaultFontSizePreset: FontSizePreset.fromWire(map["ownerDefaultFontSizePreset"], '$path.ownerDefaultFontSizePreset'),
      hasPersonaOverride: _requiredBool(map["hasPersonaOverride"], '$path.hasPersonaOverride'),
      version: _requiredInt(map["version"], '$path.version'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "themeMode": themeMode.wireName,
    "fontSizePreset": fontSizePreset.wireName,
    "source": source.wireName,
    "ownerDefaultThemeMode": ownerDefaultThemeMode.wireName,
    "ownerDefaultFontSizePreset": ownerDefaultFontSizePreset.wireName,
    "hasPersonaOverride": hasPersonaOverride,
    "version": version,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class AuthSessionGrant {
  const AuthSessionGrant({
    required this.accessToken,
    required this.refreshToken,
    required this.ownerId,
    required this.accountState,
    required this.identityOrigin,
    required this.logicalShard,
    required this.anonymousRetentionPolicy,
    required this.personaCount,
    required this.sessionRememberTtlSeconds,
    this.activePersona,
    this.accountHint,
  });

  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String accountState;
  final String identityOrigin;
  final int logicalShard;
  final String anonymousRetentionPolicy;
  final int personaCount;
  final int sessionRememberTtlSeconds;
  final ActivePersonaEnvelope? activePersona;
  final AccountHintSnapshot? accountHint;

  factory AuthSessionGrant.fromWire(Map<String, Object?> map, [String path = "AuthSessionGrant"]) {
    _rejectUnknownFields(map, const <String>{"accessToken", "refreshToken", "ownerId", "accountState", "identityOrigin", "logicalShard", "anonymousRetentionPolicy", "personaCount", "sessionRememberTtlSeconds", "activePersona", "accountHint"}, path);
    return AuthSessionGrant(
      accessToken: _requiredNonBlankString(map["accessToken"], '$path.accessToken'),
      refreshToken: _requiredNonBlankString(map["refreshToken"], '$path.refreshToken'),
      ownerId: _requiredNonBlankString(map["ownerId"], '$path.ownerId'),
      accountState: _requiredString(map["accountState"], '$path.accountState'),
      identityOrigin: _requiredString(map["identityOrigin"], '$path.identityOrigin'),
      logicalShard: _requiredInt(map["logicalShard"], '$path.logicalShard'),
      anonymousRetentionPolicy: _requiredString(map["anonymousRetentionPolicy"], '$path.anonymousRetentionPolicy'),
      personaCount: _requiredInt(map["personaCount"], '$path.personaCount'),
      sessionRememberTtlSeconds: _requiredInt(map["sessionRememberTtlSeconds"], '$path.sessionRememberTtlSeconds'),
      activePersona: map["activePersona"] == null ? null : ActivePersonaEnvelope.fromWire(_requiredObject(map["activePersona"], '$path.activePersona'), '$path.activePersona'),
      accountHint: map["accountHint"] == null ? null : AccountHintSnapshot.fromWire(_requiredObject(map["accountHint"], '$path.accountHint'), '$path.accountHint'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "accessToken": accessToken,
    "refreshToken": refreshToken,
    "ownerId": ownerId,
    "accountState": accountState,
    "identityOrigin": identityOrigin,
    "logicalShard": logicalShard,
    "anonymousRetentionPolicy": anonymousRetentionPolicy,
    "personaCount": personaCount,
    "sessionRememberTtlSeconds": sessionRememberTtlSeconds,
    if (activePersona != null) "activePersona": activePersona!.toWire(),
    if (accountHint != null) "accountHint": accountHint!.toWire(),
  };
}

final class BlockCommandResult {
  const BlockCommandResult({
    required this.targetPersonaId,
    required this.blocked,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String targetPersonaId;
  final bool blocked;
  final bool idempotentReplay;
  final DateTime updatedAt;

  factory BlockCommandResult.fromWire(Map<String, Object?> map, [String path = "BlockCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"targetPersonaId", "blocked", "idempotentReplay", "updatedAt"}, path);
    return BlockCommandResult(
      targetPersonaId: _requiredString(map["targetPersonaId"], '$path.targetPersonaId'),
      blocked: _requiredBool(map["blocked"], '$path.blocked'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": targetPersonaId,
    "blocked": blocked,
    "idempotentReplay": idempotentReplay,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class BlockedListItemView {
  const BlockedListItemView({
    required this.targetPersonaId,
    required this.displayName,
    required this.userHandle,
    this.avatarUrl,
    required this.blockedAt,
  });

  final String targetPersonaId;
  final String displayName;
  final String userHandle;
  final String? avatarUrl;
  final DateTime blockedAt;

  factory BlockedListItemView.fromWire(Map<String, Object?> map, [String path = "BlockedListItemView"]) {
    _rejectUnknownFields(map, const <String>{"targetPersonaId", "displayName", "userHandle", "avatarUrl", "blockedAt"}, path);
    return BlockedListItemView(
      targetPersonaId: _requiredString(map["targetPersonaId"], '$path.targetPersonaId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      blockedAt: _requiredTimestamp(map["blockedAt"], '$path.blockedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": targetPersonaId,
    "displayName": displayName,
    "userHandle": userHandle,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    "blockedAt": blockedAt.toUtc().toIso8601String(),
  };
}

final class BlockedUserSlice {
  const BlockedUserSlice({
    required this.items,
    this.nextCursor,
  });

  final List<BlockedListItemView> items;
  final String? nextCursor;

  factory BlockedUserSlice.fromWire(Map<String, Object?> map, [String path = "BlockedUserSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return BlockedUserSlice(
      items: List<BlockedListItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => BlockedListItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class CallSettingsView {
  const CallSettingsView({
    required this.userId,
    this.defaultIncomingCallRingtoneId,
    required this.allowCallerRingtoneOverride,
    required this.enableCallVibration,
    required this.enableGroupCallRing,
    required this.version,
    required this.updatedAt,
  });

  final String userId;
  final String? defaultIncomingCallRingtoneId;
  final bool allowCallerRingtoneOverride;
  final bool enableCallVibration;
  final bool enableGroupCallRing;
  final int version;
  final DateTime updatedAt;

  factory CallSettingsView.fromWire(Map<String, Object?> map, [String path = "CallSettingsView"]) {
    _rejectUnknownFields(map, const <String>{"userId", "defaultIncomingCallRingtoneId", "allowCallerRingtoneOverride", "enableCallVibration", "enableGroupCallRing", "version", "updatedAt"}, path);
    return CallSettingsView(
      userId: _requiredString(map["userId"], '$path.userId'),
      defaultIncomingCallRingtoneId: map["defaultIncomingCallRingtoneId"] == null ? null : _requiredString(map["defaultIncomingCallRingtoneId"], '$path.defaultIncomingCallRingtoneId'),
      allowCallerRingtoneOverride: _requiredBool(map["allowCallerRingtoneOverride"], '$path.allowCallerRingtoneOverride'),
      enableCallVibration: _requiredBool(map["enableCallVibration"], '$path.enableCallVibration'),
      enableGroupCallRing: _requiredBool(map["enableGroupCallRing"], '$path.enableGroupCallRing'),
      version: _requiredInt(map["version"], '$path.version'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    if (defaultIncomingCallRingtoneId != null) "defaultIncomingCallRingtoneId": defaultIncomingCallRingtoneId!,
    "allowCallerRingtoneOverride": allowCallerRingtoneOverride,
    "enableCallVibration": enableCallVibration,
    "enableGroupCallRing": enableGroupCallRing,
    "version": version,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class CloseAccountResultWire {
  const CloseAccountResultWire({
    required this.accountState,
    required this.closedAt,
    required this.idempotentReplay,
  });

  final AccountState accountState;
  final DateTime closedAt;
  final bool idempotentReplay;

  factory CloseAccountResultWire.fromWire(Map<String, Object?> map, [String path = "CloseAccountResultWire"]) {
    _rejectUnknownFields(map, const <String>{"accountState", "closedAt", "idempotentReplay"}, path);
    return CloseAccountResultWire(
      accountState: AccountState.fromWire(map["accountState"], '$path.accountState'),
      closedAt: _requiredTimestamp(map["closedAt"], '$path.closedAt'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "accountState": accountState.wireName,
    "closedAt": closedAt.toUtc().toIso8601String(),
    "idempotentReplay": idempotentReplay,
  };
}

final class ContactDiscoveryDismissResult {
  const ContactDiscoveryDismissResult({
    required this.status,
  });

  final DiscoveryStatus status;

  factory ContactDiscoveryDismissResult.fromWire(Map<String, Object?> map, [String path = "ContactDiscoveryDismissResult"]) {
    _rejectUnknownFields(map, const <String>{"status"}, path);
    return ContactDiscoveryDismissResult(
      status: DiscoveryStatus.fromWire(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status.wireName,
  };
}

final class ContactDiscoveryMatchResult {
  const ContactDiscoveryMatchResult({
    required this.hashedPhone,
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    this.avatarUrl,
    required this.avatarVersion,
    this.region,
    required this.relationshipCapability,
  });

  final String hashedPhone;
  final String personaId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final String? region;
  final RelationshipCapabilityView relationshipCapability;

  factory ContactDiscoveryMatchResult.fromWire(Map<String, Object?> map, [String path = "ContactDiscoveryMatchResult"]) {
    _rejectUnknownFields(map, const <String>{"hashedPhone", "personaId", "userHandle", "displayName", "avatarUrl", "avatarVersion", "region", "relationshipCapability"}, path);
    return ContactDiscoveryMatchResult(
      hashedPhone: _requiredNonBlankString(map["hashedPhone"], '$path.hashedPhone'),
      personaId: _requiredNonBlankString(map["personaId"], '$path.personaId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      avatarVersion: _requiredInt(map["avatarVersion"], '$path.avatarVersion'),
      region: map["region"] == null ? null : _requiredString(map["region"], '$path.region'),
      relationshipCapability: RelationshipCapabilityView.fromWire(_requiredObject(map["relationshipCapability"], '$path.relationshipCapability'), '$path.relationshipCapability'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "hashedPhone": hashedPhone,
    "personaId": personaId,
    "userHandle": userHandle,
    "displayName": displayName,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    "avatarVersion": avatarVersion,
    if (region != null) "region": region!,
    "relationshipCapability": relationshipCapability.toWire(),
  };
}

final class ContactDiscoveryResult {
  const ContactDiscoveryResult({
    required this.id,
    required this.status,
    required this.matchedPersonaIds,
    required this.matchCount,
    required this.matches,
    this.expireAt,
    this.completedAt,
  });

  final String id;
  final DiscoveryStatus status;
  final List<String> matchedPersonaIds;
  final int matchCount;
  final List<ContactDiscoveryMatchResult> matches;
  final DateTime? expireAt;
  final DateTime? completedAt;

  factory ContactDiscoveryResult.fromWire(Map<String, Object?> map, [String path = "ContactDiscoveryResult"]) {
    _rejectUnknownFields(map, const <String>{"id", "status", "matchedPersonaIds", "matchCount", "matches", "expireAt", "completedAt"}, path);
    return ContactDiscoveryResult(
      id: _requiredNonBlankString(map["id"], '$path.id'),
      status: DiscoveryStatus.fromWire(map["status"], '$path.status'),
      matchedPersonaIds: List<String>.unmodifiable(_requiredList(map["matchedPersonaIds"], '$path.matchedPersonaIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.matchedPersonaIds' + '[${entry.key}]'))),
      matchCount: _requiredInt(map["matchCount"], '$path.matchCount'),
      matches: List<ContactDiscoveryMatchResult>.unmodifiable(_requiredList(map["matches"], '$path.matches').asMap().entries.map((entry) => ContactDiscoveryMatchResult.fromWire(_requiredObject(entry.value, '$path.matches' + '[${entry.key}]'), '$path.matches' + '[${entry.key}]'))),
      expireAt: map["expireAt"] == null ? null : _requiredTimestamp(map["expireAt"], '$path.expireAt'),
      completedAt: map["completedAt"] == null ? null : _requiredTimestamp(map["completedAt"], '$path.completedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "status": status.wireName,
    "matchedPersonaIds": matchedPersonaIds.map((value) => value).toList(growable: false),
    "matchCount": matchCount,
    "matches": matches.map((value) => value.toWire()).toList(growable: false),
    if (expireAt != null) "expireAt": expireAt!.toUtc().toIso8601String(),
    if (completedAt != null) "completedAt": completedAt!.toUtc().toIso8601String(),
  };
}

final class ConversationAvatarSyncPatchPayload {
  const ConversationAvatarSyncPatchPayload({
    required this.conversationId,
    required this.avatarUrl,
    this.groupAvatarVersion,
    this.groupAvatarSourceHash,
  });

  final String conversationId;
  final String avatarUrl;
  final int? groupAvatarVersion;
  final String? groupAvatarSourceHash;

  factory ConversationAvatarSyncPatchPayload.fromWire(Map<String, Object?> map, [String path = "ConversationAvatarSyncPatchPayload"]) {
    _rejectUnknownFields(map, const <String>{"conversationId", "avatarUrl", "groupAvatarVersion", "groupAvatarSourceHash"}, path);
    return ConversationAvatarSyncPatchPayload(
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      groupAvatarVersion: map["groupAvatarVersion"] == null ? null : _requiredInt(map["groupAvatarVersion"], '$path.groupAvatarVersion'),
      groupAvatarSourceHash: map["groupAvatarSourceHash"] == null ? null : _requiredString(map["groupAvatarSourceHash"], '$path.groupAvatarSourceHash'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": conversationId,
    "avatarUrl": avatarUrl,
    if (groupAvatarVersion != null) "groupAvatarVersion": groupAvatarVersion!,
    if (groupAvatarSourceHash != null) "groupAvatarSourceHash": groupAvatarSourceHash!,
  };
}

final class CredentialBindingCommandResult {
  const CredentialBindingCommandResult({
    required this.credentialType,
    required this.isActive,
    required this.version,
    required this.idempotentReplay,
    this.displayLabel,
  });

  final CredentialType credentialType;
  final bool isActive;
  final int version;
  final bool idempotentReplay;
  final String? displayLabel;

  factory CredentialBindingCommandResult.fromWire(Map<String, Object?> map, [String path = "CredentialBindingCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"credentialType", "isActive", "version", "idempotentReplay", "displayLabel"}, path);
    return CredentialBindingCommandResult(
      credentialType: CredentialType.fromWire(map["credentialType"], '$path.credentialType'),
      isActive: _requiredBool(map["isActive"], '$path.isActive'),
      version: _requiredInt(map["version"], '$path.version'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
      displayLabel: map["displayLabel"] == null ? null : _requiredString(map["displayLabel"], '$path.displayLabel'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "credentialType": credentialType.wireName,
    "isActive": isActive,
    "version": version,
    "idempotentReplay": idempotentReplay,
    if (displayLabel != null) "displayLabel": displayLabel!,
  };
}

final class CredentialBindingView {
  const CredentialBindingView({
    required this.id,
    required this.credentialType,
    this.displayLabel,
    required this.isActive,
    required this.boundAt,
    required this.version,
  });

  final String id;
  final CredentialType credentialType;
  final String? displayLabel;
  final bool isActive;
  final DateTime boundAt;
  final int version;

  factory CredentialBindingView.fromWire(Map<String, Object?> map, [String path = "CredentialBindingView"]) {
    _rejectUnknownFields(map, const <String>{"id", "credentialType", "displayLabel", "isActive", "boundAt", "version"}, path);
    return CredentialBindingView(
      id: _requiredNonBlankString(map["id"], '$path.id'),
      credentialType: CredentialType.fromWire(map["credentialType"], '$path.credentialType'),
      displayLabel: map["displayLabel"] == null ? null : _requiredString(map["displayLabel"], '$path.displayLabel'),
      isActive: _requiredBool(map["isActive"], '$path.isActive'),
      boundAt: _requiredTimestamp(map["boundAt"], '$path.boundAt'),
      version: _requiredInt(map["version"], '$path.version'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "credentialType": credentialType.wireName,
    if (displayLabel != null) "displayLabel": displayLabel!,
    "isActive": isActive,
    "boundAt": boundAt.toUtc().toIso8601String(),
    "version": version,
  };
}

final class DevicePushEndpointCommandResult {
  const DevicePushEndpointCommandResult({
    required this.endpointRef,
    required this.deviceId,
    required this.endpointKind,
    required this.status,
    required this.version,
    required this.aggregateVersion,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String endpointRef;
  final String deviceId;
  final DevicePushEndpointKind endpointKind;
  final DeviceRegistrationStatus status;
  final int version;
  final int aggregateVersion;
  final bool idempotentReplay;
  final DateTime updatedAt;

  factory DevicePushEndpointCommandResult.fromWire(Map<String, Object?> map, [String path = "DevicePushEndpointCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"endpointRef", "deviceId", "endpointKind", "status", "version", "aggregateVersion", "idempotentReplay", "updatedAt"}, path);
    return DevicePushEndpointCommandResult(
      endpointRef: _requiredString(map["endpointRef"], '$path.endpointRef'),
      deviceId: _requiredString(map["deviceId"], '$path.deviceId'),
      endpointKind: DevicePushEndpointKind.fromWire(map["endpointKind"], '$path.endpointKind'),
      status: DeviceRegistrationStatus.fromWire(map["status"], '$path.status'),
      version: _requiredInt(map["version"], '$path.version'),
      aggregateVersion: _requiredInt(map["aggregateVersion"], '$path.aggregateVersion'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "endpointRef": endpointRef,
    "deviceId": deviceId,
    "endpointKind": endpointKind.wireName,
    "status": status.wireName,
    "version": version,
    "aggregateVersion": aggregateVersion,
    "idempotentReplay": idempotentReplay,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class FederatedLoginOutcome {
  const FederatedLoginOutcome({
    required this.status,
    this.session,
    this.bindingTicket,
    this.provider,
    required this.expiresInSeconds,
  });

  final FederatedLoginStatus status;
  final AuthSessionGrant? session;
  final String? bindingTicket;
  final String? provider;
  final int expiresInSeconds;

  factory FederatedLoginOutcome.fromWire(Map<String, Object?> map, [String path = "FederatedLoginOutcome"]) {
    _rejectUnknownFields(map, const <String>{"status", "session", "bindingTicket", "provider", "expiresInSeconds"}, path);
    return FederatedLoginOutcome(
      status: FederatedLoginStatus.fromWire(map["status"], '$path.status'),
      session: map["session"] == null ? null : AuthSessionGrant.fromWire(_requiredObject(map["session"], '$path.session'), '$path.session'),
      bindingTicket: map["bindingTicket"] == null ? null : _requiredString(map["bindingTicket"], '$path.bindingTicket'),
      provider: map["provider"] == null ? null : _requiredString(map["provider"], '$path.provider'),
      expiresInSeconds: _requiredInt(map["expiresInSeconds"], '$path.expiresInSeconds'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status.wireName,
    if (session != null) "session": session!.toWire(),
    if (bindingTicket != null) "bindingTicket": bindingTicket!,
    if (provider != null) "provider": provider!,
    "expiresInSeconds": expiresInSeconds,
  };
}

final class FollowCommandResult {
  const FollowCommandResult({
    required this.actorPersonaId,
    required this.targetPersonaId,
    required this.relationState,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String actorPersonaId;
  final String targetPersonaId;
  final RelationshipState relationState;
  final bool idempotentReplay;
  final DateTime updatedAt;

  factory FollowCommandResult.fromWire(Map<String, Object?> map, [String path = "FollowCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"actorPersonaId", "targetPersonaId", "relationState", "idempotentReplay", "updatedAt"}, path);
    return FollowCommandResult(
      actorPersonaId: _requiredString(map["actorPersonaId"], '$path.actorPersonaId'),
      targetPersonaId: _requiredString(map["targetPersonaId"], '$path.targetPersonaId'),
      relationState: RelationshipState.fromWire(map["relationState"], '$path.relationState'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "actorPersonaId": actorPersonaId,
    "targetPersonaId": targetPersonaId,
    "relationState": relationState.wireName,
    "idempotentReplay": idempotentReplay,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class FollowedSubjectVisitResult {
  const FollowedSubjectVisitResult({
    required this.subjectId,
    required this.subjectType,
    required this.lastVisitedAt,
    required this.hasUnreadChanges,
  });

  final String subjectId;
  final FollowSubjectKind subjectType;
  final DateTime lastVisitedAt;
  final bool hasUnreadChanges;

  factory FollowedSubjectVisitResult.fromWire(Map<String, Object?> map, [String path = "FollowedSubjectVisitResult"]) {
    _rejectUnknownFields(map, const <String>{"subjectId", "subjectType", "lastVisitedAt", "hasUnreadChanges"}, path);
    return FollowedSubjectVisitResult(
      subjectId: _requiredString(map["subjectId"], '$path.subjectId'),
      subjectType: FollowSubjectKind.fromWire(map["subjectType"], '$path.subjectType'),
      lastVisitedAt: _requiredTimestamp(map["lastVisitedAt"], '$path.lastVisitedAt'),
      hasUnreadChanges: _requiredBool(map["hasUnreadChanges"], '$path.hasUnreadChanges'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectId": subjectId,
    "subjectType": subjectType.wireName,
    "lastVisitedAt": lastVisitedAt.toUtc().toIso8601String(),
    "hasUnreadChanges": hasUnreadChanges,
  };
}

final class FollowerListItemView {
  const FollowerListItemView({
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    this.avatarUrl,
    required this.profileVisibility,
    required this.relationState,
    required this.followedAt,
    this.relationshipCapability,
  });

  final String personaId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final ProfileVisibility profileVisibility;
  final RelationshipState relationState;
  final DateTime followedAt;
  final RelationshipCapabilityView? relationshipCapability;

  factory FollowerListItemView.fromWire(Map<String, Object?> map, [String path = "FollowerListItemView"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "userHandle", "displayName", "avatarUrl", "profileVisibility", "relationState", "followedAt", "relationshipCapability"}, path);
    return FollowerListItemView(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      profileVisibility: ProfileVisibility.fromWire(map["profileVisibility"], '$path.profileVisibility'),
      relationState: RelationshipState.fromWire(map["relationState"], '$path.relationState'),
      followedAt: _requiredTimestamp(map["followedAt"], '$path.followedAt'),
      relationshipCapability: map["relationshipCapability"] == null ? null : RelationshipCapabilityView.fromWire(_requiredObject(map["relationshipCapability"], '$path.relationshipCapability'), '$path.relationshipCapability'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "userHandle": userHandle,
    "displayName": displayName,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    "profileVisibility": profileVisibility.wireName,
    "relationState": relationState.wireName,
    "followedAt": followedAt.toUtc().toIso8601String(),
    if (relationshipCapability != null) "relationshipCapability": relationshipCapability!.toWire(),
  };
}

final class FollowerRelationshipPageSlice {
  const FollowerRelationshipPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<FollowerListItemView> items;
  final String? nextCursor;

  factory FollowerRelationshipPageSlice.fromWire(Map<String, Object?> map, [String path = "FollowerRelationshipPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return FollowerRelationshipPageSlice(
      items: List<FollowerListItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => FollowerListItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class FollowingListItemView {
  const FollowingListItemView({
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    this.avatarUrl,
    required this.profileVisibility,
    required this.relationState,
    required this.followedAt,
    this.relationshipCapability,
  });

  final String personaId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final ProfileVisibility profileVisibility;
  final RelationshipState relationState;
  final DateTime followedAt;
  final RelationshipCapabilityView? relationshipCapability;

  factory FollowingListItemView.fromWire(Map<String, Object?> map, [String path = "FollowingListItemView"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "userHandle", "displayName", "avatarUrl", "profileVisibility", "relationState", "followedAt", "relationshipCapability"}, path);
    return FollowingListItemView(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      profileVisibility: ProfileVisibility.fromWire(map["profileVisibility"], '$path.profileVisibility'),
      relationState: RelationshipState.fromWire(map["relationState"], '$path.relationState'),
      followedAt: _requiredTimestamp(map["followedAt"], '$path.followedAt'),
      relationshipCapability: map["relationshipCapability"] == null ? null : RelationshipCapabilityView.fromWire(_requiredObject(map["relationshipCapability"], '$path.relationshipCapability'), '$path.relationshipCapability'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "userHandle": userHandle,
    "displayName": displayName,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    "profileVisibility": profileVisibility.wireName,
    "relationState": relationState.wireName,
    "followedAt": followedAt.toUtc().toIso8601String(),
    if (relationshipCapability != null) "relationshipCapability": relationshipCapability!.toWire(),
  };
}

final class FollowingRelationshipPageSlice {
  const FollowingRelationshipPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<FollowingListItemView> items;
  final String? nextCursor;

  factory FollowingRelationshipPageSlice.fromWire(Map<String, Object?> map, [String path = "FollowingRelationshipPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return FollowingRelationshipPageSlice(
      items: List<FollowingListItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => FollowingListItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class FollowingSubjectItemView {
  const FollowingSubjectItemView({
    required this.subjectId,
    required this.subjectType,
    required this.displayName,
    this.avatarUrl,
    this.coverUrl,
    this.subtitle,
    required this.targetRouteId,
    required this.targetObjectId,
    required this.followedAt,
    this.lastVisitedAt,
    this.latestChangedAt,
    required this.unreadChangeCount,
    required this.hasUnreadChanges,
    this.latestChangeReason,
  });

  final String subjectId;
  final FollowSubjectKind subjectType;
  final String displayName;
  final String? avatarUrl;
  final String? coverUrl;
  final String? subtitle;
  final String targetRouteId;
  final String targetObjectId;
  final DateTime followedAt;
  final DateTime? lastVisitedAt;
  final DateTime? latestChangedAt;
  final int unreadChangeCount;
  final bool hasUnreadChanges;
  final String? latestChangeReason;

  factory FollowingSubjectItemView.fromWire(Map<String, Object?> map, [String path = "FollowingSubjectItemView"]) {
    _rejectUnknownFields(map, const <String>{"subjectId", "subjectType", "displayName", "avatarUrl", "coverUrl", "subtitle", "targetRouteId", "targetObjectId", "followedAt", "lastVisitedAt", "latestChangedAt", "unreadChangeCount", "hasUnreadChanges", "latestChangeReason"}, path);
    return FollowingSubjectItemView(
      subjectId: _requiredString(map["subjectId"], '$path.subjectId'),
      subjectType: FollowSubjectKind.fromWire(map["subjectType"], '$path.subjectType'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      targetRouteId: _requiredString(map["targetRouteId"], '$path.targetRouteId'),
      targetObjectId: _requiredString(map["targetObjectId"], '$path.targetObjectId'),
      followedAt: _requiredTimestamp(map["followedAt"], '$path.followedAt'),
      lastVisitedAt: map["lastVisitedAt"] == null ? null : _requiredTimestamp(map["lastVisitedAt"], '$path.lastVisitedAt'),
      latestChangedAt: map["latestChangedAt"] == null ? null : _requiredTimestamp(map["latestChangedAt"], '$path.latestChangedAt'),
      unreadChangeCount: _requiredInt(map["unreadChangeCount"], '$path.unreadChangeCount'),
      hasUnreadChanges: _requiredBool(map["hasUnreadChanges"], '$path.hasUnreadChanges'),
      latestChangeReason: map["latestChangeReason"] == null ? null : _requiredString(map["latestChangeReason"], '$path.latestChangeReason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectId": subjectId,
    "subjectType": subjectType.wireName,
    "displayName": displayName,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (subtitle != null) "subtitle": subtitle!,
    "targetRouteId": targetRouteId,
    "targetObjectId": targetObjectId,
    "followedAt": followedAt.toUtc().toIso8601String(),
    if (lastVisitedAt != null) "lastVisitedAt": lastVisitedAt!.toUtc().toIso8601String(),
    if (latestChangedAt != null) "latestChangedAt": latestChangedAt!.toUtc().toIso8601String(),
    "unreadChangeCount": unreadChangeCount,
    "hasUnreadChanges": hasUnreadChanges,
    if (latestChangeReason != null) "latestChangeReason": latestChangeReason!,
  };
}

final class FollowingSubjectSlice {
  const FollowingSubjectSlice({
    required this.items,
    this.nextCursor,
  });

  final List<FollowingSubjectItemView> items;
  final String? nextCursor;

  factory FollowingSubjectSlice.fromWire(Map<String, Object?> map, [String path = "FollowingSubjectSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return FollowingSubjectSlice(
      items: List<FollowingSubjectItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => FollowingSubjectItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class GreetingIntersectionRef {
  const GreetingIntersectionRef({
    required this.intersectionId,
    required this.evidenceId,
    required this.sourceRef,
    required this.objectTypeRef,
    required this.objectId,
  });

  final String intersectionId;
  final String evidenceId;
  final String sourceRef;
  final String objectTypeRef;
  final String objectId;

  factory GreetingIntersectionRef.fromWire(Map<String, Object?> map, [String path = "GreetingIntersectionRef"]) {
    _rejectUnknownFields(map, const <String>{"intersectionId", "evidenceId", "sourceRef", "objectTypeRef", "objectId"}, path);
    return GreetingIntersectionRef(
      intersectionId: _requiredNonBlankString(map["intersectionId"], '$path.intersectionId'),
      evidenceId: _requiredNonBlankString(map["evidenceId"], '$path.evidenceId'),
      sourceRef: _requiredNonBlankString(map["sourceRef"], '$path.sourceRef'),
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "intersectionId": intersectionId,
    "evidenceId": evidenceId,
    "sourceRef": sourceRef,
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class GreetingRequestRecord {
  const GreetingRequestRecord({
    required this.id,
    required this.requesterPersonaId,
    required this.targetPersonaId,
    this.requestMessage,
    this.intersectionRef,
    this.intersectionSnapshot,
    required this.status,
    required this.source,
    this.promotedConversationId,
    this.expireAt,
    this.decisionAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String requesterPersonaId;
  final String targetPersonaId;
  final String? requestMessage;
  final GreetingIntersectionRef? intersectionRef;
  final GreetingIntersectionSnapshot? intersectionSnapshot;
  final GreetingRequestStatus status;
  final GreetingRequestSource source;
  final String? promotedConversationId;
  final DateTime? expireAt;
  final DateTime? decisionAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory GreetingRequestRecord.fromWire(Map<String, Object?> map, [String path = "GreetingRequestRecord"]) {
    _rejectUnknownFields(map, const <String>{"id", "requesterPersonaId", "targetPersonaId", "requestMessage", "intersectionRef", "intersectionSnapshot", "status", "source", "promotedConversationId", "expireAt", "decisionAt", "createdAt", "updatedAt"}, path);
    return GreetingRequestRecord(
      id: _requiredNonBlankString(map["id"], '$path.id'),
      requesterPersonaId: _requiredNonBlankString(map["requesterPersonaId"], '$path.requesterPersonaId'),
      targetPersonaId: _requiredNonBlankString(map["targetPersonaId"], '$path.targetPersonaId'),
      requestMessage: map["requestMessage"] == null ? null : _requiredString(map["requestMessage"], '$path.requestMessage'),
      intersectionRef: map["intersectionRef"] == null ? null : GreetingIntersectionRef.fromWire(_requiredObject(map["intersectionRef"], '$path.intersectionRef'), '$path.intersectionRef'),
      intersectionSnapshot: map["intersectionSnapshot"] == null ? null : GreetingIntersectionSnapshot.fromWire(_requiredObject(map["intersectionSnapshot"], '$path.intersectionSnapshot'), '$path.intersectionSnapshot'),
      status: GreetingRequestStatus.fromWire(map["status"], '$path.status'),
      source: GreetingRequestSource.fromWire(map["source"], '$path.source'),
      promotedConversationId: map["promotedConversationId"] == null ? null : _requiredString(map["promotedConversationId"], '$path.promotedConversationId'),
      expireAt: map["expireAt"] == null ? null : _requiredTimestamp(map["expireAt"], '$path.expireAt'),
      decisionAt: map["decisionAt"] == null ? null : _requiredTimestamp(map["decisionAt"], '$path.decisionAt'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "requesterPersonaId": requesterPersonaId,
    "targetPersonaId": targetPersonaId,
    if (requestMessage != null) "requestMessage": requestMessage!,
    if (intersectionRef != null) "intersectionRef": intersectionRef!.toWire(),
    if (intersectionSnapshot != null) "intersectionSnapshot": intersectionSnapshot!.toWire(),
    "status": status.wireName,
    "source": source.wireName,
    if (promotedConversationId != null) "promotedConversationId": promotedConversationId!,
    if (expireAt != null) "expireAt": expireAt!.toUtc().toIso8601String(),
    if (decisionAt != null) "decisionAt": decisionAt!.toUtc().toIso8601String(),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class GreetingRequestSlice {
  const GreetingRequestSlice({
    required this.items,
    this.nextCursor,
  });

  final List<GreetingRequestRecord> items;
  final String? nextCursor;

  factory GreetingRequestSlice.fromWire(Map<String, Object?> map, [String path = "GreetingRequestSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return GreetingRequestSlice(
      items: List<GreetingRequestRecord>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => GreetingRequestRecord.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ListCredentialsSlice {
  const ListCredentialsSlice({
    required this.credentials,
  });

  final List<CredentialBindingView> credentials;

  factory ListCredentialsSlice.fromWire(Map<String, Object?> map, [String path = "ListCredentialsSlice"]) {
    _rejectUnknownFields(map, const <String>{"credentials"}, path);
    return ListCredentialsSlice(
      credentials: List<CredentialBindingView>.unmodifiable(_requiredList(map["credentials"], '$path.credentials').asMap().entries.map((entry) => CredentialBindingView.fromWire(_requiredObject(entry.value, '$path.credentials' + '[${entry.key}]'), '$path.credentials' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "credentials": credentials.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ListPersonasResult {
  const ListPersonasResult({
    required this.items,
  });

  final List<PersonaManagementItemView> items;

  factory ListPersonasResult.fromWire(Map<String, Object?> map, [String path = "ListPersonasResult"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ListPersonasResult(
      items: List<PersonaManagementItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => PersonaManagementItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class LogoutAck {
  const LogoutAck({
    required this.revoked,
  });

  final bool revoked;

  factory LogoutAck.fromWire(Map<String, Object?> map, [String path = "LogoutAck"]) {
    _rejectUnknownFields(map, const <String>{"revoked"}, path);
    return LogoutAck(
      revoked: _requiredBool(map["revoked"], '$path.revoked'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "revoked": revoked,
  };
}

final class NotificationSettingsView {
  const NotificationSettingsView({
    required this.userId,
    required this.enablePush,
    required this.enableMarketing,
    this.quietHoursStart,
    this.quietHoursEnd,
    required this.version,
    required this.updatedAt,
  });

  final String userId;
  final bool enablePush;
  final bool enableMarketing;
  final String? quietHoursStart;
  final String? quietHoursEnd;
  final int version;
  final DateTime updatedAt;

  factory NotificationSettingsView.fromWire(Map<String, Object?> map, [String path = "NotificationSettingsView"]) {
    _rejectUnknownFields(map, const <String>{"userId", "enablePush", "enableMarketing", "quietHoursStart", "quietHoursEnd", "version", "updatedAt"}, path);
    return NotificationSettingsView(
      userId: _requiredString(map["userId"], '$path.userId'),
      enablePush: _requiredBool(map["enablePush"], '$path.enablePush'),
      enableMarketing: _requiredBool(map["enableMarketing"], '$path.enableMarketing'),
      quietHoursStart: map["quietHoursStart"] == null ? null : _requiredTimeOfDay(map["quietHoursStart"], '$path.quietHoursStart'),
      quietHoursEnd: map["quietHoursEnd"] == null ? null : _requiredTimeOfDay(map["quietHoursEnd"], '$path.quietHoursEnd'),
      version: _requiredInt(map["version"], '$path.version'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "enablePush": enablePush,
    "enableMarketing": enableMarketing,
    if (quietHoursStart != null) "quietHoursStart": quietHoursStart!,
    if (quietHoursEnd != null) "quietHoursEnd": quietHoursEnd!,
    "version": version,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class OneTapAccountHint {
  const OneTapAccountHint({
    required this.displayName,
    required this.avatarUrl,
    required this.maskedPhone,
    required this.identityOrigin,
  });

  final String displayName;
  final String avatarUrl;
  final String maskedPhone;
  final String identityOrigin;

  factory OneTapAccountHint.fromWire(Map<String, Object?> map, [String path = "OneTapAccountHint"]) {
    _rejectUnknownFields(map, const <String>{"displayName", "avatarUrl", "maskedPhone", "identityOrigin"}, path);
    return OneTapAccountHint(
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      maskedPhone: _requiredString(map["maskedPhone"], '$path.maskedPhone'),
      identityOrigin: _requiredString(map["identityOrigin"], '$path.identityOrigin'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "maskedPhone": maskedPhone,
    "identityOrigin": identityOrigin,
  };
}

final class OneTapLoginHint {
  const OneTapLoginHint({
    required this.state,
    required this.maskedPhone,
    required this.registered,
    required this.expiresInSeconds,
    this.accountHint,
    this.providerRequestId,
  });

  final String state;
  final String maskedPhone;
  final bool registered;
  final int expiresInSeconds;
  final OneTapAccountHint? accountHint;
  final String? providerRequestId;

  factory OneTapLoginHint.fromWire(Map<String, Object?> map, [String path = "OneTapLoginHint"]) {
    _rejectUnknownFields(map, const <String>{"state", "maskedPhone", "registered", "expiresInSeconds", "accountHint", "providerRequestId"}, path);
    return OneTapLoginHint(
      state: _requiredString(map["state"], '$path.state'),
      maskedPhone: _requiredString(map["maskedPhone"], '$path.maskedPhone'),
      registered: _requiredBool(map["registered"], '$path.registered'),
      expiresInSeconds: _requiredInt(map["expiresInSeconds"], '$path.expiresInSeconds'),
      accountHint: map["accountHint"] == null ? null : OneTapAccountHint.fromWire(_requiredObject(map["accountHint"], '$path.accountHint'), '$path.accountHint'),
      providerRequestId: map["providerRequestId"] == null ? null : _requiredString(map["providerRequestId"], '$path.providerRequestId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "state": state,
    "maskedPhone": maskedPhone,
    "registered": registered,
    "expiresInSeconds": expiresInSeconds,
    if (accountHint != null) "accountHint": accountHint!.toWire(),
    if (providerRequestId != null) "providerRequestId": providerRequestId!,
  };
}

final class OtpChallengeIssueResult {
  const OtpChallengeIssueResult({
    required this.maskedPhone,
    required this.expiresInSeconds,
    required this.deliveryStatus,
    required this.retryAfterSeconds,
    required this.requestId,
    required this.challengeId,
  });

  final String maskedPhone;
  final int expiresInSeconds;
  final OtpDeliveryStatus deliveryStatus;
  final int retryAfterSeconds;
  final String requestId;
  final String challengeId;

  factory OtpChallengeIssueResult.fromWire(Map<String, Object?> map, [String path = "OtpChallengeIssueResult"]) {
    _rejectUnknownFields(map, const <String>{"maskedPhone", "expiresInSeconds", "deliveryStatus", "retryAfterSeconds", "requestId", "challengeId"}, path);
    return OtpChallengeIssueResult(
      maskedPhone: _requiredString(map["maskedPhone"], '$path.maskedPhone'),
      expiresInSeconds: _requiredInt(map["expiresInSeconds"], '$path.expiresInSeconds'),
      deliveryStatus: OtpDeliveryStatus.fromWire(map["deliveryStatus"], '$path.deliveryStatus'),
      retryAfterSeconds: _requiredInt(map["retryAfterSeconds"], '$path.retryAfterSeconds'),
      requestId: _requiredNonBlankString(map["requestId"], '$path.requestId'),
      challengeId: _requiredNonBlankString(map["challengeId"], '$path.challengeId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "maskedPhone": maskedPhone,
    "expiresInSeconds": expiresInSeconds,
    "deliveryStatus": deliveryStatus.wireName,
    "retryAfterSeconds": retryAfterSeconds,
    "requestId": requestId,
    "challengeId": challengeId,
  };
}

final class OtpDeliveryReadiness {
  const OtpDeliveryReadiness({
    required this.availability,
    required this.retryAfterSeconds,
  });

  final OtpDeliveryAvailability availability;
  final int retryAfterSeconds;

  factory OtpDeliveryReadiness.fromWire(Map<String, Object?> map, [String path = "OtpDeliveryReadiness"]) {
    _rejectUnknownFields(map, const <String>{"availability", "retryAfterSeconds"}, path);
    return OtpDeliveryReadiness(
      availability: OtpDeliveryAvailability.fromWire(map["availability"], '$path.availability'),
      retryAfterSeconds: _requiredInt(map["retryAfterSeconds"], '$path.retryAfterSeconds'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "availability": availability.wireName,
    "retryAfterSeconds": retryAfterSeconds,
  };
}

final class PersonaLifecycleGuardView {
  const PersonaLifecycleGuardView({
    required this.personaId,
    required this.requestedAction,
    required this.allowed,
    required this.reason,
    required this.requiresSuccessor,
  });

  final String personaId;
  final PersonaLifecycleAction requestedAction;
  final bool allowed;
  final PersonaLifecycleGuardReason reason;
  final bool requiresSuccessor;

  factory PersonaLifecycleGuardView.fromWire(Map<String, Object?> map, [String path = "PersonaLifecycleGuardView"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "requestedAction", "allowed", "reason", "requiresSuccessor"}, path);
    return PersonaLifecycleGuardView(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      requestedAction: PersonaLifecycleAction.fromWire(map["requestedAction"], '$path.requestedAction'),
      allowed: _requiredBool(map["allowed"], '$path.allowed'),
      reason: PersonaLifecycleGuardReason.fromWire(map["reason"], '$path.reason'),
      requiresSuccessor: _requiredBool(map["requiresSuccessor"], '$path.requiresSuccessor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "requestedAction": requestedAction.wireName,
    "allowed": allowed,
    "reason": reason.wireName,
    "requiresSuccessor": requiresSuccessor,
  };
}

final class PersonaManagementItemView {
  const PersonaManagementItemView({
    required this.personaId,
    required this.displayName,
    this.userHandle,
    this.avatarUrl,
    this.backgroundUrl,
    this.bio,
    required this.isolationLevel,
    required this.isPrimary,
    required this.isActive,
    required this.status,
    this.retiredAt,
    required this.inheritsProfileFromOwner,
    this.overriddenProfileFields,
    this.lastProfileSyncAt,
    this.lastProfileSyncSource,
    required this.profileVisibility,
    this.purposeHint,
    required this.updatedAt,
    this.lastActivatedAt,
  });

  final String personaId;
  final String displayName;
  final String? userHandle;
  final String? avatarUrl;
  final String? backgroundUrl;
  final String? bio;
  final IsolationLevel isolationLevel;
  final bool isPrimary;
  final bool isActive;
  final PersonaStatus status;
  final DateTime? retiredAt;
  final bool inheritsProfileFromOwner;
  final List<String>? overriddenProfileFields;
  final DateTime? lastProfileSyncAt;
  final String? lastProfileSyncSource;
  final ProfileVisibility profileVisibility;
  final String? purposeHint;
  final DateTime updatedAt;
  final DateTime? lastActivatedAt;

  factory PersonaManagementItemView.fromWire(Map<String, Object?> map, [String path = "PersonaManagementItemView"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "displayName", "userHandle", "avatarUrl", "backgroundUrl", "bio", "isolationLevel", "isPrimary", "isActive", "status", "retiredAt", "inheritsProfileFromOwner", "overriddenProfileFields", "lastProfileSyncAt", "lastProfileSyncSource", "profileVisibility", "purposeHint", "updatedAt", "lastActivatedAt"}, path);
    return PersonaManagementItemView(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      userHandle: map["userHandle"] == null ? null : _requiredString(map["userHandle"], '$path.userHandle'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      backgroundUrl: map["backgroundUrl"] == null ? null : _requiredString(map["backgroundUrl"], '$path.backgroundUrl'),
      bio: map["bio"] == null ? null : _requiredString(map["bio"], '$path.bio'),
      isolationLevel: IsolationLevel.fromWire(map["isolationLevel"], '$path.isolationLevel'),
      isPrimary: _requiredBool(map["isPrimary"], '$path.isPrimary'),
      isActive: _requiredBool(map["isActive"], '$path.isActive'),
      status: PersonaStatus.fromWire(map["status"], '$path.status'),
      retiredAt: map["retiredAt"] == null ? null : _requiredTimestamp(map["retiredAt"], '$path.retiredAt'),
      inheritsProfileFromOwner: _requiredBool(map["inheritsProfileFromOwner"], '$path.inheritsProfileFromOwner'),
      overriddenProfileFields: map["overriddenProfileFields"] == null ? null : List<String>.unmodifiable(_requiredList(map["overriddenProfileFields"], '$path.overriddenProfileFields').asMap().entries.map((entry) => _requiredString(entry.value, '$path.overriddenProfileFields' + '[${entry.key}]'))),
      lastProfileSyncAt: map["lastProfileSyncAt"] == null ? null : _requiredTimestamp(map["lastProfileSyncAt"], '$path.lastProfileSyncAt'),
      lastProfileSyncSource: map["lastProfileSyncSource"] == null ? null : _requiredString(map["lastProfileSyncSource"], '$path.lastProfileSyncSource'),
      profileVisibility: ProfileVisibility.fromWire(map["profileVisibility"], '$path.profileVisibility'),
      purposeHint: map["purposeHint"] == null ? null : _requiredString(map["purposeHint"], '$path.purposeHint'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      lastActivatedAt: map["lastActivatedAt"] == null ? null : _requiredTimestamp(map["lastActivatedAt"], '$path.lastActivatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "displayName": displayName,
    if (userHandle != null) "userHandle": userHandle!,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    if (backgroundUrl != null) "backgroundUrl": backgroundUrl!,
    if (bio != null) "bio": bio!,
    "isolationLevel": isolationLevel.wireName,
    "isPrimary": isPrimary,
    "isActive": isActive,
    "status": status.wireName,
    if (retiredAt != null) "retiredAt": retiredAt!.toUtc().toIso8601String(),
    "inheritsProfileFromOwner": inheritsProfileFromOwner,
    if (overriddenProfileFields != null) "overriddenProfileFields": overriddenProfileFields!.map((value) => value).toList(growable: false),
    if (lastProfileSyncAt != null) "lastProfileSyncAt": lastProfileSyncAt!.toUtc().toIso8601String(),
    if (lastProfileSyncSource != null) "lastProfileSyncSource": lastProfileSyncSource!,
    "profileVisibility": profileVisibility.wireName,
    if (purposeHint != null) "purposeHint": purposeHint!,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (lastActivatedAt != null) "lastActivatedAt": lastActivatedAt!.toUtc().toIso8601String(),
  };
}

final class PersonaManagementQuotaView {
  const PersonaManagementQuotaView({
    required this.ownerUserId,
    required this.totalCount,
    required this.quotaLimit,
    required this.remainingCount,
    required this.activePersonaId,
    required this.primaryPersonaId,
  });

  final String ownerUserId;
  final int totalCount;
  final int quotaLimit;
  final int remainingCount;
  final String activePersonaId;
  final String primaryPersonaId;

  factory PersonaManagementQuotaView.fromWire(Map<String, Object?> map, [String path = "PersonaManagementQuotaView"]) {
    _rejectUnknownFields(map, const <String>{"ownerUserId", "totalCount", "quotaLimit", "remainingCount", "activePersonaId", "primaryPersonaId"}, path);
    return PersonaManagementQuotaView(
      ownerUserId: _requiredString(map["ownerUserId"], '$path.ownerUserId'),
      totalCount: _requiredInt(map["totalCount"], '$path.totalCount'),
      quotaLimit: _requiredInt(map["quotaLimit"], '$path.quotaLimit'),
      remainingCount: _requiredInt(map["remainingCount"], '$path.remainingCount'),
      activePersonaId: _requiredString(map["activePersonaId"], '$path.activePersonaId'),
      primaryPersonaId: _requiredString(map["primaryPersonaId"], '$path.primaryPersonaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "ownerUserId": ownerUserId,
    "totalCount": totalCount,
    "quotaLimit": quotaLimit,
    "remainingCount": remainingCount,
    "activePersonaId": activePersonaId,
    "primaryPersonaId": primaryPersonaId,
  };
}

final class PersonaManagementSummaryView {
  const PersonaManagementSummaryView({
    required this.items,
    required this.quota,
    required this.activeContext,
  });

  final List<PersonaManagementItemView> items;
  final PersonaManagementQuotaView quota;
  final ActivePersonaContextView activeContext;

  factory PersonaManagementSummaryView.fromWire(Map<String, Object?> map, [String path = "PersonaManagementSummaryView"]) {
    _rejectUnknownFields(map, const <String>{"items", "quota", "activeContext"}, path);
    return PersonaManagementSummaryView(
      items: List<PersonaManagementItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => PersonaManagementItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      quota: PersonaManagementQuotaView.fromWire(_requiredObject(map["quota"], '$path.quota'), '$path.quota'),
      activeContext: ActivePersonaContextView.fromWire(_requiredObject(map["activeContext"], '$path.activeContext'), '$path.activeContext'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "quota": quota.toWire(),
    "activeContext": activeContext.toWire(),
  };
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

  factory PersonaProfileSyncResult.fromWire(Map<String, Object?> map, [String path = "PersonaProfileSyncResult"]) {
    _rejectUnknownFields(map, const <String>{"status", "appliedCount", "fieldsMask"}, path);
    return PersonaProfileSyncResult(
      status: _requiredString(map["status"], '$path.status'),
      appliedCount: _requiredInt(map["appliedCount"], '$path.appliedCount'),
      fieldsMask: List<String>.unmodifiable(_requiredList(map["fieldsMask"], '$path.fieldsMask').asMap().entries.map((entry) => _requiredString(entry.value, '$path.fieldsMask' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status,
    "appliedCount": appliedCount,
    "fieldsMask": fieldsMask.map((value) => value).toList(growable: false),
  };
}

final class PersonaProfileView {
  const PersonaProfileView({
    required this.personaId,
    required this.subjectType,
    required this.userHandle,
    required this.displayName,
    required this.nicknameCustomized,
    this.avatarUrl,
    this.backgroundUrl,
    this.bio,
    this.headline,
    this.expertiseClaims,
    this.disclosure,
    this.identityTags,
    required this.followerCount,
    required this.followingCount,
    required this.postCount,
    required this.circleCount,
    required this.likeCount,
    required this.profileVisibility,
    required this.isolationLevel,
    required this.inheritsFromOwner,
    this.overriddenFields,
    required this.updatedAt,
  });

  final String personaId;
  final ProfileOwnerKind subjectType;
  final String userHandle;
  final String displayName;
  final bool nicknameCustomized;
  final String? avatarUrl;
  final String? backgroundUrl;
  final String? bio;
  final String? headline;
  final List<String>? expertiseClaims;
  final String? disclosure;
  final List<String>? identityTags;
  final int followerCount;
  final int followingCount;
  final int postCount;
  final int circleCount;
  final int likeCount;
  final ProfileVisibility profileVisibility;
  final IsolationLevel isolationLevel;
  final bool inheritsFromOwner;
  final List<String>? overriddenFields;
  final DateTime updatedAt;

  factory PersonaProfileView.fromWire(Map<String, Object?> map, [String path = "PersonaProfileView"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "subjectType", "userHandle", "displayName", "nicknameCustomized", "avatarUrl", "backgroundUrl", "bio", "headline", "expertiseClaims", "disclosure", "identityTags", "followerCount", "followingCount", "postCount", "circleCount", "likeCount", "profileVisibility", "isolationLevel", "inheritsFromOwner", "overriddenFields", "updatedAt"}, path);
    return PersonaProfileView(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      subjectType: ProfileOwnerKind.fromWire(map["subjectType"], '$path.subjectType'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      nicknameCustomized: _requiredBool(map["nicknameCustomized"], '$path.nicknameCustomized'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      backgroundUrl: map["backgroundUrl"] == null ? null : _requiredString(map["backgroundUrl"], '$path.backgroundUrl'),
      bio: map["bio"] == null ? null : _requiredString(map["bio"], '$path.bio'),
      headline: map["headline"] == null ? null : _requiredString(map["headline"], '$path.headline'),
      expertiseClaims: map["expertiseClaims"] == null ? null : List<String>.unmodifiable(_requiredList(map["expertiseClaims"], '$path.expertiseClaims').asMap().entries.map((entry) => _requiredString(entry.value, '$path.expertiseClaims' + '[${entry.key}]'))),
      disclosure: map["disclosure"] == null ? null : _requiredString(map["disclosure"], '$path.disclosure'),
      identityTags: map["identityTags"] == null ? null : List<String>.unmodifiable(_requiredList(map["identityTags"], '$path.identityTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.identityTags' + '[${entry.key}]'))),
      followerCount: _requiredInt(map["followerCount"], '$path.followerCount'),
      followingCount: _requiredInt(map["followingCount"], '$path.followingCount'),
      postCount: _requiredInt(map["postCount"], '$path.postCount'),
      circleCount: _requiredInt(map["circleCount"], '$path.circleCount'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      profileVisibility: ProfileVisibility.fromWire(map["profileVisibility"], '$path.profileVisibility'),
      isolationLevel: IsolationLevel.fromWire(map["isolationLevel"], '$path.isolationLevel'),
      inheritsFromOwner: _requiredBool(map["inheritsFromOwner"], '$path.inheritsFromOwner'),
      overriddenFields: map["overriddenFields"] == null ? null : List<String>.unmodifiable(_requiredList(map["overriddenFields"], '$path.overriddenFields').asMap().entries.map((entry) => _requiredString(entry.value, '$path.overriddenFields' + '[${entry.key}]'))),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "subjectType": subjectType.wireName,
    "userHandle": userHandle,
    "displayName": displayName,
    "nicknameCustomized": nicknameCustomized,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    if (backgroundUrl != null) "backgroundUrl": backgroundUrl!,
    if (bio != null) "bio": bio!,
    if (headline != null) "headline": headline!,
    if (expertiseClaims != null) "expertiseClaims": expertiseClaims!.map((value) => value).toList(growable: false),
    if (disclosure != null) "disclosure": disclosure!,
    if (identityTags != null) "identityTags": identityTags!.map((value) => value).toList(growable: false),
    "followerCount": followerCount,
    "followingCount": followingCount,
    "postCount": postCount,
    "circleCount": circleCount,
    "likeCount": likeCount,
    "profileVisibility": profileVisibility.wireName,
    "isolationLevel": isolationLevel.wireName,
    "inheritsFromOwner": inheritsFromOwner,
    if (overriddenFields != null) "overriddenFields": overriddenFields!.map((value) => value).toList(growable: false),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class PrivacySettingsView {
  const PrivacySettingsView({
    required this.userId,
    required this.allowStrangerMsg,
    required this.profileVisibility,
    this.contentLanguage,
    this.feedPreference,
    required this.assistantEnabled,
    required this.blockedKeywords,
    required this.version,
    required this.updatedAt,
  });

  final String userId;
  final bool allowStrangerMsg;
  final ProfileVisibility profileVisibility;
  final String? contentLanguage;
  final FeedPreference? feedPreference;
  final bool assistantEnabled;
  final List<String> blockedKeywords;
  final int version;
  final DateTime updatedAt;

  factory PrivacySettingsView.fromWire(Map<String, Object?> map, [String path = "PrivacySettingsView"]) {
    _rejectUnknownFields(map, const <String>{"userId", "allowStrangerMsg", "profileVisibility", "contentLanguage", "feedPreference", "assistantEnabled", "blockedKeywords", "version", "updatedAt"}, path);
    return PrivacySettingsView(
      userId: _requiredString(map["userId"], '$path.userId'),
      allowStrangerMsg: _requiredBool(map["allowStrangerMsg"], '$path.allowStrangerMsg'),
      profileVisibility: ProfileVisibility.fromWire(map["profileVisibility"], '$path.profileVisibility'),
      contentLanguage: map["contentLanguage"] == null ? null : _requiredString(map["contentLanguage"], '$path.contentLanguage'),
      feedPreference: map["feedPreference"] == null ? null : FeedPreference.fromWire(map["feedPreference"], '$path.feedPreference'),
      assistantEnabled: _requiredBool(map["assistantEnabled"], '$path.assistantEnabled'),
      blockedKeywords: List<String>.unmodifiable(_requiredList(map["blockedKeywords"], '$path.blockedKeywords').asMap().entries.map((entry) => _requiredString(entry.value, '$path.blockedKeywords' + '[${entry.key}]'))),
      version: _requiredInt(map["version"], '$path.version'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "allowStrangerMsg": allowStrangerMsg,
    "profileVisibility": profileVisibility.wireName,
    if (contentLanguage != null) "contentLanguage": contentLanguage!,
    if (feedPreference != null) "feedPreference": feedPreference!.wireName,
    "assistantEnabled": assistantEnabled,
    "blockedKeywords": blockedKeywords.map((value) => value).toList(growable: false),
    "version": version,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class ProfileCredentialSummaryWire {
  const ProfileCredentialSummaryWire({
    required this.credentialType,
    required this.displayLabel,
    required this.isBound,
  });

  final CredentialType credentialType;
  final String displayLabel;
  final bool isBound;

  factory ProfileCredentialSummaryWire.fromWire(Map<String, Object?> map, [String path = "ProfileCredentialSummaryWire"]) {
    _rejectUnknownFields(map, const <String>{"credentialType", "displayLabel", "isBound"}, path);
    return ProfileCredentialSummaryWire(
      credentialType: CredentialType.fromWire(map["credentialType"], '$path.credentialType'),
      displayLabel: _requiredString(map["displayLabel"], '$path.displayLabel'),
      isBound: _requiredBool(map["isBound"], '$path.isBound'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "credentialType": credentialType.wireName,
    "displayLabel": displayLabel,
    "isBound": isBound,
  };
}

final class ProfileEditSnapshotWire {
  const ProfileEditSnapshotWire({
    required this.ownerUserId,
    required this.personaId,
    this.avatarUrl,
    this.avatarAssetId,
    required this.avatarVersion,
    this.backgroundUrl,
    this.backgroundAssetId,
    required this.nickname,
    required this.displayName,
    this.gender,
    this.birthDate,
    this.region,
    this.regionTagRef,
    required this.userHandle,
    this.bio,
    this.identityTags,
    this.occupationTagRef,
    this.interestTagRefs,
    this.phoneCredential,
    this.qrCard,
    required this.updatedAt,
  });

  final String ownerUserId;
  final String personaId;
  final String? avatarUrl;
  final String? avatarAssetId;
  final int avatarVersion;
  final String? backgroundUrl;
  final String? backgroundAssetId;
  final String nickname;
  final String displayName;
  final Gender? gender;
  final DateTime? birthDate;
  final String? region;
  final String? regionTagRef;
  final String userHandle;
  final String? bio;
  final List<String>? identityTags;
  final String? occupationTagRef;
  final List<String>? interestTagRefs;
  final ProfileCredentialSummaryWire? phoneCredential;
  final ProfileQrCardWire? qrCard;
  final DateTime updatedAt;

  factory ProfileEditSnapshotWire.fromWire(Map<String, Object?> map, [String path = "ProfileEditSnapshotWire"]) {
    _rejectUnknownFields(map, const <String>{"ownerUserId", "personaId", "avatarUrl", "avatarAssetId", "avatarVersion", "backgroundUrl", "backgroundAssetId", "nickname", "displayName", "gender", "birthDate", "region", "regionTagRef", "userHandle", "bio", "identityTags", "occupationTagRef", "interestTagRefs", "phoneCredential", "qrCard", "updatedAt"}, path);
    return ProfileEditSnapshotWire(
      ownerUserId: _requiredString(map["ownerUserId"], '$path.ownerUserId'),
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      avatarAssetId: map["avatarAssetId"] == null ? null : _requiredString(map["avatarAssetId"], '$path.avatarAssetId'),
      avatarVersion: _requiredInt(map["avatarVersion"], '$path.avatarVersion'),
      backgroundUrl: map["backgroundUrl"] == null ? null : _requiredString(map["backgroundUrl"], '$path.backgroundUrl'),
      backgroundAssetId: map["backgroundAssetId"] == null ? null : _requiredString(map["backgroundAssetId"], '$path.backgroundAssetId'),
      nickname: _requiredString(map["nickname"], '$path.nickname'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      gender: map["gender"] == null ? null : Gender.fromWire(map["gender"], '$path.gender'),
      birthDate: map["birthDate"] == null ? null : _requiredTimestamp(map["birthDate"], '$path.birthDate'),
      region: map["region"] == null ? null : _requiredString(map["region"], '$path.region'),
      regionTagRef: map["regionTagRef"] == null ? null : _requiredString(map["regionTagRef"], '$path.regionTagRef'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      bio: map["bio"] == null ? null : _requiredString(map["bio"], '$path.bio'),
      identityTags: map["identityTags"] == null ? null : List<String>.unmodifiable(_requiredList(map["identityTags"], '$path.identityTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.identityTags' + '[${entry.key}]'))),
      occupationTagRef: map["occupationTagRef"] == null ? null : _requiredString(map["occupationTagRef"], '$path.occupationTagRef'),
      interestTagRefs: map["interestTagRefs"] == null ? null : List<String>.unmodifiable(_requiredList(map["interestTagRefs"], '$path.interestTagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.interestTagRefs' + '[${entry.key}]'))),
      phoneCredential: map["phoneCredential"] == null ? null : ProfileCredentialSummaryWire.fromWire(_requiredObject(map["phoneCredential"], '$path.phoneCredential'), '$path.phoneCredential'),
      qrCard: map["qrCard"] == null ? null : ProfileQrCardWire.fromWire(_requiredObject(map["qrCard"], '$path.qrCard'), '$path.qrCard'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "ownerUserId": ownerUserId,
    "personaId": personaId,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    if (avatarAssetId != null) "avatarAssetId": avatarAssetId!,
    "avatarVersion": avatarVersion,
    if (backgroundUrl != null) "backgroundUrl": backgroundUrl!,
    if (backgroundAssetId != null) "backgroundAssetId": backgroundAssetId!,
    "nickname": nickname,
    "displayName": displayName,
    if (gender != null) "gender": gender!.wireName,
    if (birthDate != null) "birthDate": birthDate!.toUtc().toIso8601String(),
    if (region != null) "region": region!,
    if (regionTagRef != null) "regionTagRef": regionTagRef!,
    "userHandle": userHandle,
    if (bio != null) "bio": bio!,
    if (identityTags != null) "identityTags": identityTags!.map((value) => value).toList(growable: false),
    if (occupationTagRef != null) "occupationTagRef": occupationTagRef!,
    if (interestTagRefs != null) "interestTagRefs": interestTagRefs!.map((value) => value).toList(growable: false),
    if (phoneCredential != null) "phoneCredential": phoneCredential!.toWire(),
    if (qrCard != null) "qrCard": qrCard!.toWire(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class ProfileQrCardWire {
  const ProfileQrCardWire({
    required this.publicProfileUrl,
    required this.qrPayload,
    required this.qrTokenId,
    this.avatarUrl,
    required this.displayName,
    this.region,
    this.shareText,
    this.expiresAt,
  });

  final String publicProfileUrl;
  final String qrPayload;
  final String qrTokenId;
  final String? avatarUrl;
  final String displayName;
  final String? region;
  final String? shareText;
  final DateTime? expiresAt;

  factory ProfileQrCardWire.fromWire(Map<String, Object?> map, [String path = "ProfileQrCardWire"]) {
    _rejectUnknownFields(map, const <String>{"publicProfileUrl", "qrPayload", "qrTokenId", "avatarUrl", "displayName", "region", "shareText", "expiresAt"}, path);
    return ProfileQrCardWire(
      publicProfileUrl: _requiredString(map["publicProfileUrl"], '$path.publicProfileUrl'),
      qrPayload: _requiredString(map["qrPayload"], '$path.qrPayload'),
      qrTokenId: _requiredString(map["qrTokenId"], '$path.qrTokenId'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      region: map["region"] == null ? null : _requiredString(map["region"], '$path.region'),
      shareText: map["shareText"] == null ? null : _requiredString(map["shareText"], '$path.shareText'),
      expiresAt: map["expiresAt"] == null ? null : _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "publicProfileUrl": publicProfileUrl,
    "qrPayload": qrPayload,
    "qrTokenId": qrTokenId,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    "displayName": displayName,
    if (region != null) "region": region!,
    if (shareText != null) "shareText": shareText!,
    if (expiresAt != null) "expiresAt": expiresAt!.toUtc().toIso8601String(),
  };
}

final class ProfileQrResolveWire {
  const ProfileQrResolveWire({
    required this.personaId,
    required this.userHandle,
    required this.publicProfileUrl,
    required this.scanStatus,
  });

  final String personaId;
  final String userHandle;
  final String publicProfileUrl;
  final String scanStatus;

  factory ProfileQrResolveWire.fromWire(Map<String, Object?> map, [String path = "ProfileQrResolveWire"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "userHandle", "publicProfileUrl", "scanStatus"}, path);
    return ProfileQrResolveWire(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      publicProfileUrl: _requiredString(map["publicProfileUrl"], '$path.publicProfileUrl'),
      scanStatus: _requiredString(map["scanStatus"], '$path.scanStatus'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "userHandle": userHandle,
    "publicProfileUrl": publicProfileUrl,
    "scanStatus": scanStatus,
  };
}

final class ProfileUpdateProposalCommandResult {
  const ProfileUpdateProposalCommandResult({
    required this.proposalId,
    required this.version,
    required this.status,
    required this.replayed,
  });

  final String proposalId;
  final int version;
  final ProposalStatus status;
  final bool replayed;

  factory ProfileUpdateProposalCommandResult.fromWire(Map<String, Object?> map, [String path = "ProfileUpdateProposalCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"proposalId", "version", "status", "replayed"}, path);
    return ProfileUpdateProposalCommandResult(
      proposalId: _requiredString(map["proposalId"], '$path.proposalId'),
      version: _requiredInt(map["version"], '$path.version'),
      status: ProposalStatus.fromWire(map["status"], '$path.status'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "proposalId": proposalId,
    "version": version,
    "status": status.wireName,
    "replayed": replayed,
  };
}

final class ProfileUpdateProposalSlice {
  const ProfileUpdateProposalSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ProfileUpdateProposalView> items;
  final String? nextCursor;

  factory ProfileUpdateProposalSlice.fromWire(Map<String, Object?> map, [String path = "ProfileUpdateProposalSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return ProfileUpdateProposalSlice(
      items: List<ProfileUpdateProposalView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ProfileUpdateProposalView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ProfileUpdateProposalView {
  const ProfileUpdateProposalView({
    required this.id,
    required this.personaId,
    required this.source,
    required this.reason,
    required this.evidenceRefs,
    required this.impactScope,
    required this.createdBy,
    required this.status,
    this.displayName,
    this.bio,
    this.avatarMediaAssetId,
    this.backgroundMediaAssetId,
    this.isPrivate,
    this.isolationLevel,
    this.purposeHint,
    this.reviewedBy,
    this.applyAuditId,
    this.rollbackDeadline,
    this.rollbackAuditId,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
    this.resolvedAt,
  });

  final String id;
  final String personaId;
  final ProposalSource source;
  final String reason;
  final List<String> evidenceRefs;
  final List<String> impactScope;
  final String createdBy;
  final ProposalStatus status;
  final String? displayName;
  final String? bio;
  final String? avatarMediaAssetId;
  final String? backgroundMediaAssetId;
  final bool? isPrivate;
  final String? isolationLevel;
  final String? purposeHint;
  final String? reviewedBy;
  final String? applyAuditId;
  final DateTime? rollbackDeadline;
  final String? rollbackAuditId;
  final int version;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;

  factory ProfileUpdateProposalView.fromWire(Map<String, Object?> map, [String path = "ProfileUpdateProposalView"]) {
    _rejectUnknownFields(map, const <String>{"id", "personaId", "source", "reason", "evidenceRefs", "impactScope", "createdBy", "status", "displayName", "bio", "avatarMediaAssetId", "backgroundMediaAssetId", "isPrivate", "isolationLevel", "purposeHint", "reviewedBy", "applyAuditId", "rollbackDeadline", "rollbackAuditId", "version", "createdAt", "updatedAt", "resolvedAt"}, path);
    return ProfileUpdateProposalView(
      id: _requiredString(map["id"], '$path.id'),
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      source: ProposalSource.fromWire(map["source"], '$path.source'),
      reason: _requiredString(map["reason"], '$path.reason'),
      evidenceRefs: List<String>.unmodifiable(_requiredList(map["evidenceRefs"], '$path.evidenceRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.evidenceRefs' + '[${entry.key}]'))),
      impactScope: List<String>.unmodifiable(_requiredList(map["impactScope"], '$path.impactScope').asMap().entries.map((entry) => _requiredString(entry.value, '$path.impactScope' + '[${entry.key}]'))),
      createdBy: _requiredString(map["createdBy"], '$path.createdBy'),
      status: ProposalStatus.fromWire(map["status"], '$path.status'),
      displayName: map["displayName"] == null ? null : _requiredString(map["displayName"], '$path.displayName'),
      bio: map["bio"] == null ? null : _requiredString(map["bio"], '$path.bio'),
      avatarMediaAssetId: map["avatarMediaAssetId"] == null ? null : _requiredString(map["avatarMediaAssetId"], '$path.avatarMediaAssetId'),
      backgroundMediaAssetId: map["backgroundMediaAssetId"] == null ? null : _requiredString(map["backgroundMediaAssetId"], '$path.backgroundMediaAssetId'),
      isPrivate: map["isPrivate"] == null ? null : _requiredBool(map["isPrivate"], '$path.isPrivate'),
      isolationLevel: map["isolationLevel"] == null ? null : _requiredString(map["isolationLevel"], '$path.isolationLevel'),
      purposeHint: map["purposeHint"] == null ? null : _requiredString(map["purposeHint"], '$path.purposeHint'),
      reviewedBy: map["reviewedBy"] == null ? null : _requiredString(map["reviewedBy"], '$path.reviewedBy'),
      applyAuditId: map["applyAuditId"] == null ? null : _requiredString(map["applyAuditId"], '$path.applyAuditId'),
      rollbackDeadline: map["rollbackDeadline"] == null ? null : _requiredTimestamp(map["rollbackDeadline"], '$path.rollbackDeadline'),
      rollbackAuditId: map["rollbackAuditId"] == null ? null : _requiredString(map["rollbackAuditId"], '$path.rollbackAuditId'),
      version: _requiredInt(map["version"], '$path.version'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      resolvedAt: map["resolvedAt"] == null ? null : _requiredTimestamp(map["resolvedAt"], '$path.resolvedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "personaId": personaId,
    "source": source.wireName,
    "reason": reason,
    "evidenceRefs": evidenceRefs.map((value) => value).toList(growable: false),
    "impactScope": impactScope.map((value) => value).toList(growable: false),
    "createdBy": createdBy,
    "status": status.wireName,
    if (displayName != null) "displayName": displayName!,
    if (bio != null) "bio": bio!,
    if (avatarMediaAssetId != null) "avatarMediaAssetId": avatarMediaAssetId!,
    if (backgroundMediaAssetId != null) "backgroundMediaAssetId": backgroundMediaAssetId!,
    if (isPrivate != null) "isPrivate": isPrivate!,
    if (isolationLevel != null) "isolationLevel": isolationLevel!,
    if (purposeHint != null) "purposeHint": purposeHint!,
    if (reviewedBy != null) "reviewedBy": reviewedBy!,
    if (applyAuditId != null) "applyAuditId": applyAuditId!,
    if (rollbackDeadline != null) "rollbackDeadline": rollbackDeadline!.toUtc().toIso8601String(),
    if (rollbackAuditId != null) "rollbackAuditId": rollbackAuditId!,
    "version": version,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (resolvedAt != null) "resolvedAt": resolvedAt!.toUtc().toIso8601String(),
  };
}

final class ProfileUpdateSnapshot {
  const ProfileUpdateSnapshot({
    required this.userId,
    required this.nickname,
    required this.nicknameCustomized,
    required this.profileVersion,
    this.accountState,
    this.avatarUrl,
    this.avatarAssetId,
    required this.avatarVersion,
    this.backgroundUrl,
    this.backgroundAssetId,
    this.bio,
    required this.identityTags,
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
  final DateTime? birthDate;
  final String? region;
  final String? regionTagRef;
  final String? status;
  final DateTime? updatedAt;

  factory ProfileUpdateSnapshot.fromWire(Map<String, Object?> map, [String path = "ProfileUpdateSnapshot"]) {
    _rejectUnknownFields(map, const <String>{"userId", "nickname", "nicknameCustomized", "profileVersion", "accountState", "avatarUrl", "avatarAssetId", "avatarVersion", "backgroundUrl", "backgroundAssetId", "bio", "identityTags", "gender", "birthDate", "region", "regionTagRef", "status", "updatedAt"}, path);
    return ProfileUpdateSnapshot(
      userId: _requiredNonBlankString(map["userId"], '$path.userId'),
      nickname: _requiredString(map["nickname"], '$path.nickname'),
      nicknameCustomized: _requiredBool(map["nicknameCustomized"], '$path.nicknameCustomized'),
      profileVersion: _requiredInt(map["profileVersion"], '$path.profileVersion'),
      accountState: map["accountState"] == null ? null : _requiredString(map["accountState"], '$path.accountState'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      avatarAssetId: map["avatarAssetId"] == null ? null : _requiredString(map["avatarAssetId"], '$path.avatarAssetId'),
      avatarVersion: _requiredInt(map["avatarVersion"], '$path.avatarVersion'),
      backgroundUrl: map["backgroundUrl"] == null ? null : _requiredString(map["backgroundUrl"], '$path.backgroundUrl'),
      backgroundAssetId: map["backgroundAssetId"] == null ? null : _requiredString(map["backgroundAssetId"], '$path.backgroundAssetId'),
      bio: map["bio"] == null ? null : _requiredString(map["bio"], '$path.bio'),
      identityTags: List<String>.unmodifiable(_requiredList(map["identityTags"], '$path.identityTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.identityTags' + '[${entry.key}]'))),
      gender: map["gender"] == null ? null : _requiredString(map["gender"], '$path.gender'),
      birthDate: map["birthDate"] == null ? null : _requiredTimestamp(map["birthDate"], '$path.birthDate'),
      region: map["region"] == null ? null : _requiredString(map["region"], '$path.region'),
      regionTagRef: map["regionTagRef"] == null ? null : _requiredString(map["regionTagRef"], '$path.regionTagRef'),
      status: map["status"] == null ? null : _requiredString(map["status"], '$path.status'),
      updatedAt: map["updatedAt"] == null ? null : _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "nickname": nickname,
    "nicknameCustomized": nicknameCustomized,
    "profileVersion": profileVersion,
    if (accountState != null) "accountState": accountState!,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    if (avatarAssetId != null) "avatarAssetId": avatarAssetId!,
    "avatarVersion": avatarVersion,
    if (backgroundUrl != null) "backgroundUrl": backgroundUrl!,
    if (backgroundAssetId != null) "backgroundAssetId": backgroundAssetId!,
    if (bio != null) "bio": bio!,
    "identityTags": identityTags.map((value) => value).toList(growable: false),
    if (gender != null) "gender": gender!,
    if (birthDate != null) "birthDate": birthDate!.toUtc().toIso8601String(),
    if (region != null) "region": region!,
    if (regionTagRef != null) "regionTagRef": regionTagRef!,
    if (status != null) "status": status!,
    if (updatedAt != null) "updatedAt": updatedAt!.toUtc().toIso8601String(),
  };
}

final class PullUserSyncSlice {
  const PullUserSyncSlice({
    required this.patches,
    required this.latestSyncSeq,
    required this.hasMore,
    required this.requiresResync,
  });

  final List<UserSyncPatch> patches;
  final int latestSyncSeq;
  final bool hasMore;
  final bool requiresResync;

  factory PullUserSyncSlice.fromWire(Map<String, Object?> map, [String path = "PullUserSyncSlice"]) {
    _rejectUnknownFields(map, const <String>{"patches", "latestSyncSeq", "hasMore", "requiresResync"}, path);
    return PullUserSyncSlice(
      patches: List<UserSyncPatch>.unmodifiable(_requiredList(map["patches"], '$path.patches').asMap().entries.map((entry) => UserSyncPatch.fromWire(_requiredObject(entry.value, '$path.patches' + '[${entry.key}]'), '$path.patches' + '[${entry.key}]'))),
      latestSyncSeq: _requiredInt(map["latestSyncSeq"], '$path.latestSyncSeq'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
      requiresResync: _requiredBool(map["requiresResync"], '$path.requiresResync'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "patches": patches.map((value) => value.toWire()).toList(growable: false),
    "latestSyncSeq": latestSyncSeq,
    "hasMore": hasMore,
    "requiresResync": requiresResync,
  };
}

final class RelationshipCapabilityView {
  const RelationshipCapabilityView({
    required this.viewerPersonaId,
    required this.targetPersonaId,
    required this.relationState,
    required this.canFollow,
    required this.canUnfollow,
    required this.canFollowBack,
    required this.canGreet,
    required this.canOpenConversation,
    required this.canCreateDirectConversation,
    required this.canSendMessage,
    required this.hasPendingGreeting,
    required this.hasFormalConversation,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
    required this.isBlocked,
    required this.isBlockedBy,
  });

  final String viewerPersonaId;
  final String targetPersonaId;
  final RelationshipState relationState;
  final bool canFollow;
  final bool canUnfollow;
  final bool canFollowBack;
  final bool canGreet;
  final bool canOpenConversation;
  final bool canCreateDirectConversation;
  final bool canSendMessage;
  final bool hasPendingGreeting;
  final bool hasFormalConversation;
  final bool canStartVoiceCall;
  final bool canStartVideoCall;
  final bool isBlocked;
  final bool isBlockedBy;

  factory RelationshipCapabilityView.fromWire(Map<String, Object?> map, [String path = "RelationshipCapabilityView"]) {
    _rejectUnknownFields(map, const <String>{"viewerPersonaId", "targetPersonaId", "relationState", "canFollow", "canUnfollow", "canFollowBack", "canGreet", "canOpenConversation", "canCreateDirectConversation", "canSendMessage", "hasPendingGreeting", "hasFormalConversation", "canStartVoiceCall", "canStartVideoCall", "isBlocked", "isBlockedBy"}, path);
    return RelationshipCapabilityView(
      viewerPersonaId: _requiredString(map["viewerPersonaId"], '$path.viewerPersonaId'),
      targetPersonaId: _requiredString(map["targetPersonaId"], '$path.targetPersonaId'),
      relationState: RelationshipState.fromWire(map["relationState"], '$path.relationState'),
      canFollow: _requiredBool(map["canFollow"], '$path.canFollow'),
      canUnfollow: _requiredBool(map["canUnfollow"], '$path.canUnfollow'),
      canFollowBack: _requiredBool(map["canFollowBack"], '$path.canFollowBack'),
      canGreet: _requiredBool(map["canGreet"], '$path.canGreet'),
      canOpenConversation: _requiredBool(map["canOpenConversation"], '$path.canOpenConversation'),
      canCreateDirectConversation: _requiredBool(map["canCreateDirectConversation"], '$path.canCreateDirectConversation'),
      canSendMessage: _requiredBool(map["canSendMessage"], '$path.canSendMessage'),
      hasPendingGreeting: _requiredBool(map["hasPendingGreeting"], '$path.hasPendingGreeting'),
      hasFormalConversation: _requiredBool(map["hasFormalConversation"], '$path.hasFormalConversation'),
      canStartVoiceCall: _requiredBool(map["canStartVoiceCall"], '$path.canStartVoiceCall'),
      canStartVideoCall: _requiredBool(map["canStartVideoCall"], '$path.canStartVideoCall'),
      isBlocked: _requiredBool(map["isBlocked"], '$path.isBlocked'),
      isBlockedBy: _requiredBool(map["isBlockedBy"], '$path.isBlockedBy'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "viewerPersonaId": viewerPersonaId,
    "targetPersonaId": targetPersonaId,
    "relationState": relationState.wireName,
    "canFollow": canFollow,
    "canUnfollow": canUnfollow,
    "canFollowBack": canFollowBack,
    "canGreet": canGreet,
    "canOpenConversation": canOpenConversation,
    "canCreateDirectConversation": canCreateDirectConversation,
    "canSendMessage": canSendMessage,
    "hasPendingGreeting": hasPendingGreeting,
    "hasFormalConversation": hasFormalConversation,
    "canStartVoiceCall": canStartVoiceCall,
    "canStartVideoCall": canStartVideoCall,
    "isBlocked": isBlocked,
    "isBlockedBy": isBlockedBy,
  };
}

final class SearchSocialRelationsResult {
  const SearchSocialRelationsResult({
    required this.items,
    required this.cursor,
  });

  final List<SocialRelationSearchItemView> items;
  final String cursor;

  factory SearchSocialRelationsResult.fromWire(Map<String, Object?> map, [String path = "SearchSocialRelationsResult"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return SearchSocialRelationsResult(
      items: List<SocialRelationSearchItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => SocialRelationSearchItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "cursor": cursor,
  };
}

final class SocialRelationSearchItemView {
  const SocialRelationSearchItemView({
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    this.avatarUrl,
    this.headline,
    required this.chatAvailable,
    required this.relationshipCapability,
  });

  final String personaId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final String? headline;
  final bool chatAvailable;
  final RelationshipCapabilityView relationshipCapability;

  factory SocialRelationSearchItemView.fromWire(Map<String, Object?> map, [String path = "SocialRelationSearchItemView"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "userHandle", "displayName", "avatarUrl", "headline", "chatAvailable", "relationshipCapability"}, path);
    return SocialRelationSearchItemView(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null ? null : _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      headline: map["headline"] == null ? null : _requiredString(map["headline"], '$path.headline'),
      chatAvailable: _requiredBool(map["chatAvailable"], '$path.chatAvailable'),
      relationshipCapability: RelationshipCapabilityView.fromWire(_requiredObject(map["relationshipCapability"], '$path.relationshipCapability'), '$path.relationshipCapability'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "userHandle": userHandle,
    "displayName": displayName,
    if (avatarUrl != null) "avatarUrl": avatarUrl!,
    if (headline != null) "headline": headline!,
    "chatAvailable": chatAvailable,
    "relationshipCapability": relationshipCapability.toWire(),
  };
}

final class SubjectFollowCommandResult {
  const SubjectFollowCommandResult({
    required this.personaId,
    required this.subjectType,
    required this.subjectId,
    required this.state,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String personaId;
  final SubjectFollowTargetKind subjectType;
  final String subjectId;
  final SubjectFollowState state;
  final bool idempotentReplay;
  final DateTime updatedAt;

  factory SubjectFollowCommandResult.fromWire(Map<String, Object?> map, [String path = "SubjectFollowCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "subjectType", "subjectId", "state", "idempotentReplay", "updatedAt"}, path);
    return SubjectFollowCommandResult(
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      subjectType: SubjectFollowTargetKind.fromWire(map["subjectType"], '$path.subjectType'),
      subjectId: _requiredString(map["subjectId"], '$path.subjectId'),
      state: SubjectFollowState.fromWire(map["state"], '$path.state'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "subjectType": subjectType.wireName,
    "subjectId": subjectId,
    "state": state.wireName,
    "idempotentReplay": idempotentReplay,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TokenRefreshGrant {
  const TokenRefreshGrant({
    required this.accessToken,
    required this.refreshToken,
    required this.sessionRememberTtlSeconds,
  });

  final String accessToken;
  final String refreshToken;
  final int sessionRememberTtlSeconds;

  factory TokenRefreshGrant.fromWire(Map<String, Object?> map, [String path = "TokenRefreshGrant"]) {
    _rejectUnknownFields(map, const <String>{"accessToken", "refreshToken", "sessionRememberTtlSeconds"}, path);
    return TokenRefreshGrant(
      accessToken: _requiredNonBlankString(map["accessToken"], '$path.accessToken'),
      refreshToken: _requiredNonBlankString(map["refreshToken"], '$path.refreshToken'),
      sessionRememberTtlSeconds: _requiredInt(map["sessionRememberTtlSeconds"], '$path.sessionRememberTtlSeconds'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "accessToken": accessToken,
    "refreshToken": refreshToken,
    "sessionRememberTtlSeconds": sessionRememberTtlSeconds,
  };
}

final class UserAvatarSyncPatchPayload {
  const UserAvatarSyncPatchPayload({
    required this.userId,
    required this.avatarUrl,
    required this.avatarVersion,
  });

  final String userId;
  final String avatarUrl;
  final int avatarVersion;

  factory UserAvatarSyncPatchPayload.fromWire(Map<String, Object?> map, [String path = "UserAvatarSyncPatchPayload"]) {
    _rejectUnknownFields(map, const <String>{"userId", "avatarUrl", "avatarVersion"}, path);
    return UserAvatarSyncPatchPayload(
      userId: _requiredString(map["userId"], '$path.userId'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      avatarVersion: _requiredInt(map["avatarVersion"], '$path.avatarVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "avatarUrl": avatarUrl,
    "avatarVersion": avatarVersion,
  };
}

final class UserHomepageBundleWire {
  const UserHomepageBundleWire({
    required this.profile,
    required this.stats,
    this.relationshipCapability,
    required this.tabCounts,
    required this.viewerContext,
    required this.cacheVersion,
  });

  final PersonaProfileView profile;
  final UserProfileStatsWire stats;
  final RelationshipCapabilityView? relationshipCapability;
  final UserHomepageTabCountsWire tabCounts;
  final UserHomepageViewerContextWire viewerContext;
  final String cacheVersion;

  factory UserHomepageBundleWire.fromWire(Map<String, Object?> map, [String path = "UserHomepageBundleWire"]) {
    _rejectUnknownFields(map, const <String>{"profile", "stats", "relationshipCapability", "tabCounts", "viewerContext", "cacheVersion"}, path);
    return UserHomepageBundleWire(
      profile: PersonaProfileView.fromWire(_requiredObject(map["profile"], '$path.profile'), '$path.profile'),
      stats: UserProfileStatsWire.fromWire(_requiredObject(map["stats"], '$path.stats'), '$path.stats'),
      relationshipCapability: map["relationshipCapability"] == null ? null : RelationshipCapabilityView.fromWire(_requiredObject(map["relationshipCapability"], '$path.relationshipCapability'), '$path.relationshipCapability'),
      tabCounts: UserHomepageTabCountsWire.fromWire(_requiredObject(map["tabCounts"], '$path.tabCounts'), '$path.tabCounts'),
      viewerContext: UserHomepageViewerContextWire.fromWire(_requiredObject(map["viewerContext"], '$path.viewerContext'), '$path.viewerContext'),
      cacheVersion: _requiredString(map["cacheVersion"], '$path.cacheVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "profile": profile.toWire(),
    "stats": stats.toWire(),
    if (relationshipCapability != null) "relationshipCapability": relationshipCapability!.toWire(),
    "tabCounts": tabCounts.toWire(),
    "viewerContext": viewerContext.toWire(),
    "cacheVersion": cacheVersion,
  };
}

final class UserHomepageTabCountsWire {
  const UserHomepageTabCountsWire({
    required this.worksCount,
    required this.likesCount,
    required this.circlesCount,
    required this.collectionsCount,
  });

  final int worksCount;
  final int likesCount;
  final int circlesCount;
  final int collectionsCount;

  factory UserHomepageTabCountsWire.fromWire(Map<String, Object?> map, [String path = "UserHomepageTabCountsWire"]) {
    _rejectUnknownFields(map, const <String>{"worksCount", "likesCount", "circlesCount", "collectionsCount"}, path);
    return UserHomepageTabCountsWire(
      worksCount: _requiredInt(map["worksCount"], '$path.worksCount'),
      likesCount: _requiredInt(map["likesCount"], '$path.likesCount'),
      circlesCount: _requiredInt(map["circlesCount"], '$path.circlesCount'),
      collectionsCount: _requiredInt(map["collectionsCount"], '$path.collectionsCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "worksCount": worksCount,
    "likesCount": likesCount,
    "circlesCount": circlesCount,
    "collectionsCount": collectionsCount,
  };
}

final class UserHomepageViewerContextWire {
  const UserHomepageViewerContextWire({
    required this.viewerPersonaId,
    required this.isOwner,
    required this.isGuest,
    required this.relationToTarget,
    required this.canViewFullProfile,
  });

  final String viewerPersonaId;
  final bool isOwner;
  final bool isGuest;
  final RelationshipState relationToTarget;
  final bool canViewFullProfile;

  factory UserHomepageViewerContextWire.fromWire(Map<String, Object?> map, [String path = "UserHomepageViewerContextWire"]) {
    _rejectUnknownFields(map, const <String>{"viewerPersonaId", "isOwner", "isGuest", "relationToTarget", "canViewFullProfile"}, path);
    return UserHomepageViewerContextWire(
      viewerPersonaId: _requiredString(map["viewerPersonaId"], '$path.viewerPersonaId'),
      isOwner: _requiredBool(map["isOwner"], '$path.isOwner'),
      isGuest: _requiredBool(map["isGuest"], '$path.isGuest'),
      relationToTarget: RelationshipState.fromWire(map["relationToTarget"], '$path.relationToTarget'),
      canViewFullProfile: _requiredBool(map["canViewFullProfile"], '$path.canViewFullProfile'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "viewerPersonaId": viewerPersonaId,
    "isOwner": isOwner,
    "isGuest": isGuest,
    "relationToTarget": relationToTarget.wireName,
    "canViewFullProfile": canViewFullProfile,
  };
}

final class UserProfileStatsWire {
  const UserProfileStatsWire({
    required this.followingCount,
    required this.circleCount,
    required this.followerCount,
    required this.likeCount,
    required this.postCount,
  });

  final int followingCount;
  final int circleCount;
  final int followerCount;
  final int likeCount;
  final int postCount;

  factory UserProfileStatsWire.fromWire(Map<String, Object?> map, [String path = "UserProfileStatsWire"]) {
    _rejectUnknownFields(map, const <String>{"followingCount", "circleCount", "followerCount", "likeCount", "postCount"}, path);
    return UserProfileStatsWire(
      followingCount: _requiredInt(map["followingCount"], '$path.followingCount'),
      circleCount: _requiredInt(map["circleCount"], '$path.circleCount'),
      followerCount: _requiredInt(map["followerCount"], '$path.followerCount'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      postCount: _requiredInt(map["postCount"], '$path.postCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "followingCount": followingCount,
    "circleCount": circleCount,
    "followerCount": followerCount,
    "likeCount": likeCount,
    "postCount": postCount,
  };
}

final class UserSettingsCommandResult {
  const UserSettingsCommandResult({
    required this.userId,
    required this.version,
    required this.idempotentReplay,
  });

  final String userId;
  final int version;
  final bool idempotentReplay;

  factory UserSettingsCommandResult.fromWire(Map<String, Object?> map, [String path = "UserSettingsCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"userId", "version", "idempotentReplay"}, path);
    return UserSettingsCommandResult(
      userId: _requiredString(map["userId"], '$path.userId'),
      version: _requiredInt(map["version"], '$path.version'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "version": version,
    "idempotentReplay": idempotentReplay,
  };
}

final class UserSyncPatch {
  const UserSyncPatch({
    required this.syncSeq,
    required this.kind,
    this.userAvatarUpdated,
    this.conversationAvatarUpdated,
    required this.occurredAt,
  });

  final int syncSeq;
  final UserSyncPatchKind kind;
  final UserAvatarSyncPatchPayload? userAvatarUpdated;
  final ConversationAvatarSyncPatchPayload? conversationAvatarUpdated;
  final DateTime occurredAt;

  factory UserSyncPatch.fromWire(Map<String, Object?> map, [String path = "UserSyncPatch"]) {
    _rejectUnknownFields(map, const <String>{"syncSeq", "kind", "userAvatarUpdated", "conversationAvatarUpdated", "occurredAt"}, path);
    return UserSyncPatch(
      syncSeq: _requiredInt(map["syncSeq"], '$path.syncSeq'),
      kind: UserSyncPatchKind.fromWire(map["kind"], '$path.kind'),
      userAvatarUpdated: map["userAvatarUpdated"] == null ? null : UserAvatarSyncPatchPayload.fromWire(_requiredObject(map["userAvatarUpdated"], '$path.userAvatarUpdated'), '$path.userAvatarUpdated'),
      conversationAvatarUpdated: map["conversationAvatarUpdated"] == null ? null : ConversationAvatarSyncPatchPayload.fromWire(_requiredObject(map["conversationAvatarUpdated"], '$path.conversationAvatarUpdated'), '$path.conversationAvatarUpdated'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "syncSeq": syncSeq,
    "kind": kind.wireName,
    if (userAvatarUpdated != null) "userAvatarUpdated": userAvatarUpdated!.toWire(),
    if (conversationAvatarUpdated != null) "conversationAvatarUpdated": conversationAvatarUpdated!.toWire(),
    "occurredAt": occurredAt.toUtc().toIso8601String(),
  };
}

final class WhitelistedResearchSession {
  const WhitelistedResearchSession({
    required this.subjectHash,
    required this.attestationId,
    required this.expiresAt,
  });

  final String subjectHash;
  final String attestationId;
  final DateTime expiresAt;

  factory WhitelistedResearchSession.fromWire(Map<String, Object?> map, [String path = "WhitelistedResearchSession"]) {
    _rejectUnknownFields(map, const <String>{"subjectHash", "attestationId", "expiresAt"}, path);
    return WhitelistedResearchSession(
      subjectHash: _requiredNonBlankString(map["subjectHash"], '$path.subjectHash'),
      attestationId: _requiredNonBlankString(map["attestationId"], '$path.attestationId'),
      expiresAt: _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectHash": subjectHash,
    "attestationId": attestationId,
    "expiresAt": expiresAt.toUtc().toIso8601String(),
  };
}

ActivePersonaContextView decodeActivePersonaContextView(Object? response) =>
    ActivePersonaContextView.fromWire(_requiredObject(response, "ActivePersonaContextView"), "ActivePersonaContextView");

AlipayAuthorizationGrant decodeAlipayAuthorizationGrant(Object? response) =>
    AlipayAuthorizationGrant.fromWire(_requiredObject(response, "AlipayAuthorizationGrant"), "AlipayAuthorizationGrant");

AppearanceSettingsView decodeAppearanceSettingsView(Object? response) =>
    AppearanceSettingsView.fromWire(_requiredObject(response, "AppearanceSettingsView"), "AppearanceSettingsView");

AuthSessionGrant decodeAuthSessionGrant(Object? response) =>
    AuthSessionGrant.fromWire(_requiredObject(response, "AuthSessionGrant"), "AuthSessionGrant");

BlockCommandResult decodeBlockCommandResult(Object? response) =>
    BlockCommandResult.fromWire(_requiredObject(response, "BlockCommandResult"), "BlockCommandResult");

BlockedUserSlice decodeBlockedUserSlice(Object? response) =>
    BlockedUserSlice.fromWire(_requiredObject(response, "BlockedUserSlice"), "BlockedUserSlice");

CallSettingsView decodeCallSettingsView(Object? response) =>
    CallSettingsView.fromWire(_requiredObject(response, "CallSettingsView"), "CallSettingsView");

CloseAccountResultWire decodeCloseAccountResultWire(Object? response) =>
    CloseAccountResultWire.fromWire(_requiredObject(response, "CloseAccountResultWire"), "CloseAccountResultWire");

ContactDiscoveryDismissResult decodeContactDiscoveryDismissResult(Object? response) =>
    ContactDiscoveryDismissResult.fromWire(_requiredObject(response, "ContactDiscoveryDismissResult"), "ContactDiscoveryDismissResult");

ContactDiscoveryResult decodeContactDiscoveryResult(Object? response) =>
    ContactDiscoveryResult.fromWire(_requiredObject(response, "ContactDiscoveryResult"), "ContactDiscoveryResult");

CredentialBindingCommandResult decodeCredentialBindingCommandResult(Object? response) =>
    CredentialBindingCommandResult.fromWire(_requiredObject(response, "CredentialBindingCommandResult"), "CredentialBindingCommandResult");

DevicePushEndpointCommandResult decodeDevicePushEndpointCommandResult(Object? response) =>
    DevicePushEndpointCommandResult.fromWire(_requiredObject(response, "DevicePushEndpointCommandResult"), "DevicePushEndpointCommandResult");

FederatedLoginOutcome decodeFederatedLoginOutcome(Object? response) =>
    FederatedLoginOutcome.fromWire(_requiredObject(response, "FederatedLoginOutcome"), "FederatedLoginOutcome");

FollowCommandResult decodeFollowCommandResult(Object? response) =>
    FollowCommandResult.fromWire(_requiredObject(response, "FollowCommandResult"), "FollowCommandResult");

FollowedSubjectVisitResult decodeFollowedSubjectVisitResult(Object? response) =>
    FollowedSubjectVisitResult.fromWire(_requiredObject(response, "FollowedSubjectVisitResult"), "FollowedSubjectVisitResult");

FollowerRelationshipPageSlice decodeFollowerRelationshipPageSlice(Object? response) =>
    FollowerRelationshipPageSlice.fromWire(_requiredObject(response, "FollowerRelationshipPageSlice"), "FollowerRelationshipPageSlice");

FollowingRelationshipPageSlice decodeFollowingRelationshipPageSlice(Object? response) =>
    FollowingRelationshipPageSlice.fromWire(_requiredObject(response, "FollowingRelationshipPageSlice"), "FollowingRelationshipPageSlice");

FollowingSubjectSlice decodeFollowingSubjectSlice(Object? response) =>
    FollowingSubjectSlice.fromWire(_requiredObject(response, "FollowingSubjectSlice"), "FollowingSubjectSlice");

GreetingRequestRecord decodeGreetingRequestRecord(Object? response) =>
    GreetingRequestRecord.fromWire(_requiredObject(response, "GreetingRequestRecord"), "GreetingRequestRecord");

GreetingRequestSlice decodeGreetingRequestSlice(Object? response) =>
    GreetingRequestSlice.fromWire(_requiredObject(response, "GreetingRequestSlice"), "GreetingRequestSlice");

ListCredentialsSlice decodeListCredentialsSlice(Object? response) =>
    ListCredentialsSlice.fromWire(_requiredObject(response, "ListCredentialsSlice"), "ListCredentialsSlice");

ListPersonasResult decodeListPersonasResult(Object? response) =>
    ListPersonasResult.fromWire(_requiredObject(response, "ListPersonasResult"), "ListPersonasResult");

LogoutAck decodeLogoutAck(Object? response) =>
    LogoutAck.fromWire(_requiredObject(response, "LogoutAck"), "LogoutAck");

NotificationSettingsView decodeNotificationSettingsView(Object? response) =>
    NotificationSettingsView.fromWire(_requiredObject(response, "NotificationSettingsView"), "NotificationSettingsView");

OneTapLoginHint decodeOneTapLoginHint(Object? response) =>
    OneTapLoginHint.fromWire(_requiredObject(response, "OneTapLoginHint"), "OneTapLoginHint");

OtpChallengeIssueResult decodeOtpChallengeIssueResult(Object? response) =>
    OtpChallengeIssueResult.fromWire(_requiredObject(response, "OtpChallengeIssueResult"), "OtpChallengeIssueResult");

OtpDeliveryReadiness decodeOtpDeliveryReadiness(Object? response) =>
    OtpDeliveryReadiness.fromWire(_requiredObject(response, "OtpDeliveryReadiness"), "OtpDeliveryReadiness");

PersonaLifecycleGuardView decodePersonaLifecycleGuardView(Object? response) =>
    PersonaLifecycleGuardView.fromWire(_requiredObject(response, "PersonaLifecycleGuardView"), "PersonaLifecycleGuardView");

PersonaManagementItemView decodePersonaManagementItemView(Object? response) =>
    PersonaManagementItemView.fromWire(_requiredObject(response, "PersonaManagementItemView"), "PersonaManagementItemView");

PersonaManagementSummaryView decodePersonaManagementSummaryView(Object? response) =>
    PersonaManagementSummaryView.fromWire(_requiredObject(response, "PersonaManagementSummaryView"), "PersonaManagementSummaryView");

PersonaProfileSyncResult decodePersonaProfileSyncResult(Object? response) =>
    PersonaProfileSyncResult.fromWire(_requiredObject(response, "PersonaProfileSyncResult"), "PersonaProfileSyncResult");

PersonaProfileView decodePersonaProfileView(Object? response) =>
    PersonaProfileView.fromWire(_requiredObject(response, "PersonaProfileView"), "PersonaProfileView");

PrivacySettingsView decodePrivacySettingsView(Object? response) =>
    PrivacySettingsView.fromWire(_requiredObject(response, "PrivacySettingsView"), "PrivacySettingsView");

ProfileEditSnapshotWire decodeProfileEditSnapshotWire(Object? response) =>
    ProfileEditSnapshotWire.fromWire(_requiredObject(response, "ProfileEditSnapshotWire"), "ProfileEditSnapshotWire");

ProfileQrCardWire decodeProfileQrCardWire(Object? response) =>
    ProfileQrCardWire.fromWire(_requiredObject(response, "ProfileQrCardWire"), "ProfileQrCardWire");

ProfileQrResolveWire decodeProfileQrResolveWire(Object? response) =>
    ProfileQrResolveWire.fromWire(_requiredObject(response, "ProfileQrResolveWire"), "ProfileQrResolveWire");

ProfileUpdateProposalCommandResult decodeProfileUpdateProposalCommandResult(Object? response) =>
    ProfileUpdateProposalCommandResult.fromWire(_requiredObject(response, "ProfileUpdateProposalCommandResult"), "ProfileUpdateProposalCommandResult");

ProfileUpdateProposalSlice decodeProfileUpdateProposalSlice(Object? response) =>
    ProfileUpdateProposalSlice.fromWire(_requiredObject(response, "ProfileUpdateProposalSlice"), "ProfileUpdateProposalSlice");

ProfileUpdateProposalView decodeProfileUpdateProposalView(Object? response) =>
    ProfileUpdateProposalView.fromWire(_requiredObject(response, "ProfileUpdateProposalView"), "ProfileUpdateProposalView");

ProfileUpdateSnapshot decodeProfileUpdateSnapshot(Object? response) =>
    ProfileUpdateSnapshot.fromWire(_requiredObject(response, "ProfileUpdateSnapshot"), "ProfileUpdateSnapshot");

PullUserSyncSlice decodePullUserSyncSlice(Object? response) =>
    PullUserSyncSlice.fromWire(_requiredObject(response, "PullUserSyncSlice"), "PullUserSyncSlice");

RelationshipCapabilityView decodeRelationshipCapabilityView(Object? response) =>
    RelationshipCapabilityView.fromWire(_requiredObject(response, "RelationshipCapabilityView"), "RelationshipCapabilityView");

SearchSocialRelationsResult decodeSearchSocialRelationsResult(Object? response) =>
    SearchSocialRelationsResult.fromWire(_requiredObject(response, "SearchSocialRelationsResult"), "SearchSocialRelationsResult");

SubjectFollowCommandResult decodeSubjectFollowCommandResult(Object? response) =>
    SubjectFollowCommandResult.fromWire(_requiredObject(response, "SubjectFollowCommandResult"), "SubjectFollowCommandResult");

TokenRefreshGrant decodeTokenRefreshGrant(Object? response) =>
    TokenRefreshGrant.fromWire(_requiredObject(response, "TokenRefreshGrant"), "TokenRefreshGrant");

UserHomepageBundleWire decodeUserHomepageBundleWire(Object? response) =>
    UserHomepageBundleWire.fromWire(_requiredObject(response, "UserHomepageBundleWire"), "UserHomepageBundleWire");

UserSettingsCommandResult decodeUserSettingsCommandResult(Object? response) =>
    UserSettingsCommandResult.fromWire(_requiredObject(response, "UserSettingsCommandResult"), "UserSettingsCommandResult");

WhitelistedResearchSession decodeWhitelistedResearchSession(Object? response) =>
    WhitelistedResearchSession.fromWire(_requiredObject(response, "WhitelistedResearchSession"), "WhitelistedResearchSession");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

String _requiredTimeOfDay(Object? value, String path) {
  final result = _requiredString(value, path);
  if (!RegExp(r'^([01][0-9]|2[0-3]):[0-5][0-9]$').hasMatch(result)) {
    throw FormatException('$path must be a HH:MM wall-clock time');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
