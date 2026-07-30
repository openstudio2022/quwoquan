// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/user_settings_contracts.dart';

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

Object _encodeGeneratedNullableMutation<T extends Object>(
  NullableSettingMutation<T> mutation,
  Object Function(T value) encoder,
) {
  if (mutation.clearsValue) return '';
  final value = mutation.value;
  if (value == null) {
    throw StateError('setting mutation must contain a value or clear marker');
  }
  return encoder(value);
}

final class UpdateAppearanceSettingsCommand {
  const UpdateAppearanceSettingsCommand({
    required ThemeModeSetting themeMode,
    required FontSizePreset fontSizePreset,
    required AppearanceApplyScope applyScope,
  }) : themeMode = themeMode,
       fontSizePreset = fontSizePreset,
       applyScope = applyScope;

  final ThemeModeSetting themeMode;
  final FontSizePreset fontSizePreset;
  final AppearanceApplyScope applyScope;
}

final class UpdateCallSettingsCommand {
  const UpdateCallSettingsCommand({
    NullableSettingMutation<OfficialRingtoneId>? defaultIncomingCallRingtoneId,
    bool? allowCallerRingtoneOverride,
    bool? enableCallVibration,
    bool? enableGroupCallRing,
  }) : defaultIncomingCallRingtoneId = defaultIncomingCallRingtoneId,
       allowCallerRingtoneOverride = allowCallerRingtoneOverride,
       enableCallVibration = enableCallVibration,
       enableGroupCallRing = enableGroupCallRing;

  final NullableSettingMutation<OfficialRingtoneId>? defaultIncomingCallRingtoneId;
  final bool? allowCallerRingtoneOverride;
  final bool? enableCallVibration;
  final bool? enableGroupCallRing;
}

final class UpdateNotificationSettingsCommand {
  const UpdateNotificationSettingsCommand({
    bool? enablePush,
    bool? enableMarketing,
    NullableSettingMutation<QuietHoursTime>? quietHoursStart,
    NullableSettingMutation<QuietHoursTime>? quietHoursEnd,
  }) : enablePush = enablePush,
       enableMarketing = enableMarketing,
       quietHoursStart = quietHoursStart,
       quietHoursEnd = quietHoursEnd;

  final bool? enablePush;
  final bool? enableMarketing;
  final NullableSettingMutation<QuietHoursTime>? quietHoursStart;
  final NullableSettingMutation<QuietHoursTime>? quietHoursEnd;
}

final class UpdatePrivacySettingsCommand {
  UpdatePrivacySettingsCommand({
    bool? allowStrangerMsg,
    ProfileVisibility? profileVisibility,
    List<String>? blockedKeywords,
    bool? assistantEnabled,
  }) : allowStrangerMsg = allowStrangerMsg,
       profileVisibility = profileVisibility,
       blockedKeywords = blockedKeywords == null ? null : _normalizeGeneratedTextList(blockedKeywords, deduplicate: true),
       assistantEnabled = assistantEnabled {
  }

  final bool? allowStrangerMsg;
  final ProfileVisibility? profileVisibility;
  final List<String>? blockedKeywords;
  final bool? assistantEnabled;
}

final class UserSettingsQuery {
  const UserSettingsQuery();
}

CloudOperationRequestPayload encodeUserUserSettingsGetAppearanceSettingsGeneratedRequest(UserSettingsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserSettingsGetCallSettingsGeneratedRequest(UserSettingsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserSettingsGetNotificationSettingsGeneratedRequest(UserSettingsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserSettingsGetPrivacySettingsGeneratedRequest(UserSettingsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserSettingsUpdateAppearanceSettingsGeneratedRequest(UpdateAppearanceSettingsCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "themeMode": switch (request.themeMode) { ThemeModeSetting.system => "system", ThemeModeSetting.light => "light", ThemeModeSetting.dark => "dark", },
      "fontSizePreset": switch (request.fontSizePreset) { FontSizePreset.xs => "xs", FontSizePreset.sm => "sm", FontSizePreset.md => "md", FontSizePreset.lg => "lg", FontSizePreset.xl => "xl", },
      "applyScope": switch (request.applyScope) { AppearanceApplyScope.allAccounts => "all_accounts", AppearanceApplyScope.currentPersona => "current_persona", AppearanceApplyScope.inheritOwnerDefault => "inherit_owner_default", },
    },
  );
}

CloudOperationRequestPayload encodeUserUserSettingsUpdateCallSettingsGeneratedRequest(UpdateCallSettingsCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.defaultIncomingCallRingtoneId != null) "defaultIncomingCallRingtoneId": _encodeGeneratedNullableMutation(request.defaultIncomingCallRingtoneId!, (value) => value.wireValue),
      if (request.allowCallerRingtoneOverride != null) "allowCallerRingtoneOverride": request.allowCallerRingtoneOverride!,
      if (request.enableCallVibration != null) "enableCallVibration": request.enableCallVibration!,
      if (request.enableGroupCallRing != null) "enableGroupCallRing": request.enableGroupCallRing!,
    },
  );
}

CloudOperationRequestPayload encodeUserUserSettingsUpdateNotificationSettingsGeneratedRequest(UpdateNotificationSettingsCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.enablePush != null) "enablePush": request.enablePush!,
      if (request.enableMarketing != null) "enableMarketing": request.enableMarketing!,
      if (request.quietHoursStart != null) "quietHoursStart": _encodeGeneratedNullableMutation(request.quietHoursStart!, (value) => value.wireValue),
      if (request.quietHoursEnd != null) "quietHoursEnd": _encodeGeneratedNullableMutation(request.quietHoursEnd!, (value) => value.wireValue),
    },
  );
}

CloudOperationRequestPayload encodeUserUserSettingsUpdatePrivacySettingsGeneratedRequest(UpdatePrivacySettingsCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.allowStrangerMsg != null) "allowStrangerMsg": request.allowStrangerMsg!,
      if (request.profileVisibility != null) "profileVisibility": switch (request.profileVisibility!) { ProfileVisibility.public => "public", ProfileVisibility.friends => "friends", ProfileVisibility.privateProfile => "private", },
      if (request.blockedKeywords != null) "blockedKeywords": request.blockedKeywords!.map((value) => value).toList(growable: false),
      if (request.assistantEnabled != null) "assistantEnabled": request.assistantEnabled!,
    },
  );
}

