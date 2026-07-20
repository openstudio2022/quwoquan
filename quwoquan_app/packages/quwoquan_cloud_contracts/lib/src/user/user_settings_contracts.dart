import '../operation_request_payload.dart';

/// UserSettings 聚合命令的 pure contracts。
/// 真相源：contracts/metadata/user/user_settings/{service,fields}.yaml。
/// 单聚合 4 场景命名 set；服务端内部 version CAS，公开请求不接收调用方版本字段。
/// PATCH 语义：仅编码非 null 字段。

enum ProfileVisibility {
  public('public'),
  friends('friends'),
  privateProfile('private');

  const ProfileVisibility(this.wireValue);

  final String wireValue;
}

enum FeedPreference {
  recommend('recommend'),
  chronological('chronological');

  const FeedPreference(this.wireValue);

  final String wireValue;
}

enum ThemeModeSetting {
  system('system'),
  light('light'),
  dark('dark');

  const ThemeModeSetting(this.wireValue);

  final String wireValue;
}

enum FontSizePreset {
  xs('xs'),
  sm('sm'),
  md('md'),
  lg('lg'),
  xl('xl');

  const FontSizePreset(this.wireValue);

  final String wireValue;
}

enum AppearanceSource {
  ownerDefault('owner_default'),
  subOverride('sub_override'),
  systemDefault('system_default');

  const AppearanceSource(this.wireValue);

  final String wireValue;
}

enum AppearanceApplyScope {
  allAccounts('all_accounts'),
  currentSubAccount('current_sub_account'),
  inheritOwnerDefault('inherit_owner_default');

  const AppearanceApplyScope(this.wireValue);

  final String wireValue;
}

/// metadata `time` 的端侧强类型表示，wire 固定为 HH:mm。
final class QuietHoursTime {
  const QuietHoursTime._({required this.hour, required this.minute});

  factory QuietHoursTime({required int hour, required int minute}) {
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      throw ArgumentError('quiet hours must use a valid hour and minute');
    }
    return QuietHoursTime._(hour: hour, minute: minute);
  }

  factory QuietHoursTime.parse(String value) {
    final normalized = value.trim();
    final match = RegExp(r'^([01]\d|2[0-3]):([0-5]\d)$').firstMatch(normalized);
    if (match == null) {
      throw FormatException('quiet hours must use HH:mm: $value');
    }
    return QuietHoursTime._(
      hour: int.parse(match.group(1)!),
      minute: int.parse(match.group(2)!),
    );
  }

  final int hour;
  final int minute;

  String get wireValue =>
      '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';

  @override
  bool operator ==(Object other) =>
      other is QuietHoursTime && other.hour == hour && other.minute == minute;

  @override
  int get hashCode => Object.hash(hour, minute);

  @override
  String toString() => wireValue;
}

/// 仅接受 metadata/domain 约束的官方铃声命名空间。
final class OfficialRingtoneId {
  OfficialRingtoneId(String value) : value = _normalizeRingtoneId(value);

  OfficialRingtoneId._(this.value);

  factory OfficialRingtoneId.fromWire(String value) {
    try {
      return OfficialRingtoneId._(_normalizeRingtoneId(value));
    } on ArgumentError {
      throw FormatException(
        'defaultIncomingCallRingtoneId must use the official namespace',
      );
    }
  }

  final String value;

  String get wireValue => value;

  @override
  bool operator ==(Object other) =>
      other is OfficialRingtoneId && other.value == value;

  @override
  int get hashCode => value.hashCode;

  @override
  String toString() => value;
}

/// PATCH 中 nullable 字段的三态：null=不修改、set=赋值、clear=清除。
final class NullableSettingMutation<T extends Object> {
  const NullableSettingMutation.set(this.value) : clearsValue = false;

  const NullableSettingMutation.clear() : value = null, clearsValue = true;

  final T? value;
  final bool clearsValue;
}

final class UpdateNotificationSettingsCommand {
  const UpdateNotificationSettingsCommand({
    this.enablePush,
    this.enableMarketing,
    this.quietHoursStart,
    this.quietHoursEnd,
  });

  final bool? enablePush;
  final bool? enableMarketing;
  final NullableSettingMutation<QuietHoursTime>? quietHoursStart;
  final NullableSettingMutation<QuietHoursTime>? quietHoursEnd;
}

final class UpdatePrivacySettingsCommand {
  UpdatePrivacySettingsCommand({
    this.allowStrangerMsg,
    this.profileVisibility,
    List<String>? blockedKeywords,
    this.assistantEnabled,
  }) : blockedKeywords = blockedKeywords == null
           ? null
           : List<String>.unmodifiable(_normalizeKeywords(blockedKeywords));

  final bool? allowStrangerMsg;
  final ProfileVisibility? profileVisibility;
  final List<String>? blockedKeywords;
  final bool? assistantEnabled;
}

final class UpdateCallSettingsCommand {
  const UpdateCallSettingsCommand({
    this.defaultIncomingCallRingtoneId,
    this.allowCallerRingtoneOverride,
    this.enableCallVibration,
    this.enableGroupCallRing,
  });

  final NullableSettingMutation<OfficialRingtoneId>?
  defaultIncomingCallRingtoneId;
  final bool? allowCallerRingtoneOverride;
  final bool? enableCallVibration;
  final bool? enableGroupCallRing;
}

final class UpdateAppearanceSettingsCommand {
  const UpdateAppearanceSettingsCommand({
    required this.themeMode,
    required this.fontSizePreset,
    required this.applyScope,
  });

  final ThemeModeSetting themeMode;
  final FontSizePreset fontSizePreset;
  final AppearanceApplyScope applyScope;
}

/// 通知/隐私/通话设置命令的稳定提交回执；页面读投影为单一真相源。
final class UserSettingsCommandResult {
  const UserSettingsCommandResult({
    required this.userId,
    required this.version,
    required this.idempotentReplay,
  });

  final String userId;
  final int version;
  final bool idempotentReplay;
}

/// 外观设置命令回执（保留 scope 合成语义：source/owner 默认值回读）。
final class AppearanceSettingsView {
  const AppearanceSettingsView({
    required this.themeMode,
    required this.fontSizePreset,
    required this.source,
    required this.ownerDefaultThemeMode,
    required this.ownerDefaultFontSizePreset,
    required this.hasSubAccountOverride,
    required this.version,
    required this.updatedAt,
  });

  final ThemeModeSetting themeMode;
  final FontSizePreset fontSizePreset;
  final AppearanceSource source;
  final ThemeModeSetting ownerDefaultThemeMode;
  final FontSizePreset ownerDefaultFontSizePreset;
  final bool hasSubAccountOverride;
  final int version;
  final DateTime updatedAt;
}

abstract interface class UserSettingsCommandWriter {
  Future<UserSettingsCommandResult> updateNotificationSettings(
    UpdateNotificationSettingsCommand command,
  );

  Future<UserSettingsCommandResult> updatePrivacySettings(
    UpdatePrivacySettingsCommand command,
  );

  Future<UserSettingsCommandResult> updateCallSettings(
    UpdateCallSettingsCommand command,
  );

  Future<AppearanceSettingsView> updateAppearanceSettings(
    UpdateAppearanceSettingsCommand command,
  );
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
  final QuietHoursTime? quietHoursStart;
  final QuietHoursTime? quietHoursEnd;
  final int version;
  final DateTime updatedAt;

  NotificationSettingsView copyWith({
    bool? enablePush,
    bool? enableMarketing,
    NullableSettingMutation<QuietHoursTime>? quietHoursStart,
    NullableSettingMutation<QuietHoursTime>? quietHoursEnd,
    int? version,
    DateTime? updatedAt,
  }) => NotificationSettingsView(
    userId: userId,
    enablePush: enablePush ?? this.enablePush,
    enableMarketing: enableMarketing ?? this.enableMarketing,
    quietHoursStart: _applyNullableMutation(
      this.quietHoursStart,
      quietHoursStart,
    ),
    quietHoursEnd: _applyNullableMutation(this.quietHoursEnd, quietHoursEnd),
    version: version ?? this.version,
    updatedAt: updatedAt ?? this.updatedAt,
  );
}

final class PrivacySettingsView {
  PrivacySettingsView({
    required this.userId,
    required this.allowStrangerMsg,
    required this.profileVisibility,
    this.contentLanguage,
    this.feedPreference,
    required this.assistantEnabled,
    List<String> blockedKeywords = const <String>[],
    required this.version,
    required this.updatedAt,
  }) : blockedKeywords = List<String>.unmodifiable(blockedKeywords);

  final String userId;
  final bool allowStrangerMsg;
  final ProfileVisibility profileVisibility;
  final String? contentLanguage;
  final FeedPreference? feedPreference;
  final bool assistantEnabled;
  final List<String> blockedKeywords;
  final int version;
  final DateTime updatedAt;

  PrivacySettingsView copyWith({
    bool? allowStrangerMsg,
    ProfileVisibility? profileVisibility,
    bool? assistantEnabled,
    List<String>? blockedKeywords,
    int? version,
    DateTime? updatedAt,
  }) => PrivacySettingsView(
    userId: userId,
    allowStrangerMsg: allowStrangerMsg ?? this.allowStrangerMsg,
    profileVisibility: profileVisibility ?? this.profileVisibility,
    contentLanguage: contentLanguage,
    feedPreference: feedPreference,
    assistantEnabled: assistantEnabled ?? this.assistantEnabled,
    blockedKeywords: blockedKeywords ?? this.blockedKeywords,
    version: version ?? this.version,
    updatedAt: updatedAt ?? this.updatedAt,
  );
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
  final OfficialRingtoneId? defaultIncomingCallRingtoneId;
  final bool allowCallerRingtoneOverride;
  final bool enableCallVibration;
  final bool enableGroupCallRing;
  final int version;
  final DateTime updatedAt;

  CallSettingsView copyWith({
    NullableSettingMutation<OfficialRingtoneId>? defaultIncomingCallRingtoneId,
    bool? allowCallerRingtoneOverride,
    bool? enableCallVibration,
    bool? enableGroupCallRing,
    int? version,
    DateTime? updatedAt,
  }) => CallSettingsView(
    userId: userId,
    defaultIncomingCallRingtoneId: _applyNullableMutation(
      this.defaultIncomingCallRingtoneId,
      defaultIncomingCallRingtoneId,
    ),
    allowCallerRingtoneOverride:
        allowCallerRingtoneOverride ?? this.allowCallerRingtoneOverride,
    enableCallVibration: enableCallVibration ?? this.enableCallVibration,
    enableGroupCallRing: enableGroupCallRing ?? this.enableGroupCallRing,
    version: version ?? this.version,
    updatedAt: updatedAt ?? this.updatedAt,
  );
}

/// UserSettings 的四个对象级 named Reader；同时作为无 body GET 的 ABI marker。
final class UserSettingsQuery {
  const UserSettingsQuery();
}

abstract interface class UserSettingsQueryReader {
  Future<NotificationSettingsView> getNotificationSettings();

  Future<PrivacySettingsView> getPrivacySettings();

  Future<CallSettingsView> getCallSettings();

  Future<AppearanceSettingsView> getAppearanceSettings();
}

CloudOperationRequestPayload encodeUserSettingsQuery(UserSettingsQuery query) =>
    const CloudOperationRequestPayload(body: null);

NotificationSettingsView decodeNotificationSettingsView(Object? value) {
  final map = _object(value, 'NotificationSettingsView');
  _only(map, const <String>{
    'userId',
    'enablePush',
    'enableMarketing',
    'quietHoursStart',
    'quietHoursEnd',
    'version',
    'updatedAt',
  });
  return NotificationSettingsView(
    userId: _string(map, 'userId'),
    enablePush: _bool(map, 'enablePush'),
    enableMarketing: _bool(map, 'enableMarketing'),
    quietHoursStart: _optionalQuietHoursTime(map, 'quietHoursStart'),
    quietHoursEnd: _optionalQuietHoursTime(map, 'quietHoursEnd'),
    version: _nonNegativeInt(map, 'version'),
    updatedAt: _timestamp(map, 'updatedAt'),
  );
}

PrivacySettingsView decodePrivacySettingsView(Object? value) {
  final map = _object(value, 'PrivacySettingsView');
  _only(map, const <String>{
    'userId',
    'allowStrangerMsg',
    'profileVisibility',
    'contentLanguage',
    'feedPreference',
    'assistantEnabled',
    'blockedKeywords',
    'version',
    'updatedAt',
  });
  final feedPreference = _optionalString(map, 'feedPreference');
  return PrivacySettingsView(
    userId: _string(map, 'userId'),
    allowStrangerMsg: _bool(map, 'allowStrangerMsg'),
    profileVisibility: _enumValue(
      map,
      'profileVisibility',
      ProfileVisibility.values,
      (value) => value.wireValue,
    ),
    contentLanguage: _optionalString(map, 'contentLanguage'),
    feedPreference: feedPreference == null
        ? null
        : _enumFromString<FeedPreference>(
            feedPreference,
            'feedPreference',
            FeedPreference.values,
            (FeedPreference value) => value.wireValue,
          ),
    assistantEnabled: _bool(map, 'assistantEnabled'),
    blockedKeywords: _stringList(map, 'blockedKeywords'),
    version: _nonNegativeInt(map, 'version'),
    updatedAt: _timestamp(map, 'updatedAt'),
  );
}

CallSettingsView decodeCallSettingsView(Object? value) {
  final map = _object(value, 'CallSettingsView');
  _only(map, const <String>{
    'userId',
    'defaultIncomingCallRingtoneId',
    'allowCallerRingtoneOverride',
    'enableCallVibration',
    'enableGroupCallRing',
    'version',
    'updatedAt',
  });
  final ringtone = _optionalString(map, 'defaultIncomingCallRingtoneId');
  return CallSettingsView(
    userId: _string(map, 'userId'),
    defaultIncomingCallRingtoneId: ringtone == null
        ? null
        : OfficialRingtoneId.fromWire(ringtone),
    allowCallerRingtoneOverride: _bool(map, 'allowCallerRingtoneOverride'),
    enableCallVibration: _bool(map, 'enableCallVibration'),
    enableGroupCallRing: _bool(map, 'enableGroupCallRing'),
    version: _nonNegativeInt(map, 'version'),
    updatedAt: _timestamp(map, 'updatedAt'),
  );
}

CloudOperationRequestPayload encodeUpdateNotificationSettingsCommand(
  UpdateNotificationSettingsCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    if (command.enablePush != null) 'enablePush': command.enablePush,
    if (command.enableMarketing != null)
      'enableMarketing': command.enableMarketing,
    if (command.quietHoursStart != null)
      'quietHoursStart': _nullableMutationWire(
        command.quietHoursStart!,
        (value) => value.wireValue,
      ),
    if (command.quietHoursEnd != null)
      'quietHoursEnd': _nullableMutationWire(
        command.quietHoursEnd!,
        (value) => value.wireValue,
      ),
  },
);

CloudOperationRequestPayload encodeUpdatePrivacySettingsCommand(
  UpdatePrivacySettingsCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    if (command.allowStrangerMsg != null)
      'allowStrangerMsg': command.allowStrangerMsg,
    if (command.profileVisibility != null)
      'profileVisibility': command.profileVisibility!.wireValue,
    if (command.blockedKeywords != null)
      'blockedKeywords': command.blockedKeywords,
    if (command.assistantEnabled != null)
      'assistantEnabled': command.assistantEnabled,
  },
);

CloudOperationRequestPayload encodeUpdateCallSettingsCommand(
  UpdateCallSettingsCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    if (command.defaultIncomingCallRingtoneId != null)
      'defaultIncomingCallRingtoneId': _nullableMutationWire(
        command.defaultIncomingCallRingtoneId!,
        (value) => value.wireValue,
      ),
    if (command.allowCallerRingtoneOverride != null)
      'allowCallerRingtoneOverride': command.allowCallerRingtoneOverride,
    if (command.enableCallVibration != null)
      'enableCallVibration': command.enableCallVibration,
    if (command.enableGroupCallRing != null)
      'enableGroupCallRing': command.enableGroupCallRing,
  },
);

CloudOperationRequestPayload encodeUpdateAppearanceSettingsCommand(
  UpdateAppearanceSettingsCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'themeMode': command.themeMode.wireValue,
    'fontSizePreset': command.fontSizePreset.wireValue,
    'applyScope': command.applyScope.wireValue,
  },
);

UserSettingsCommandResult decodeUserSettingsCommandResult(Object? value) {
  final map = _object(value, 'UserSettingsCommandResult');
  _only(map, const <String>{'userId', 'version', 'idempotentReplay'});
  return UserSettingsCommandResult(
    userId: _string(map, 'userId'),
    version: _nonNegativeInt(map, 'version'),
    idempotentReplay: _bool(map, 'idempotentReplay'),
  );
}

AppearanceSettingsView decodeAppearanceSettingsView(Object? value) {
  final map = _object(value, 'AppearanceSettingsView');
  _only(map, const <String>{
    'themeMode',
    'fontSizePreset',
    'source',
    'ownerDefaultThemeMode',
    'ownerDefaultFontSizePreset',
    'hasSubAccountOverride',
    'version',
    'updatedAt',
  });
  return AppearanceSettingsView(
    themeMode: _enumValue(
      map,
      'themeMode',
      ThemeModeSetting.values,
      (value) => value.wireValue,
    ),
    fontSizePreset: _enumValue(
      map,
      'fontSizePreset',
      FontSizePreset.values,
      (value) => value.wireValue,
    ),
    source: _enumValue(
      map,
      'source',
      AppearanceSource.values,
      (value) => value.wireValue,
    ),
    ownerDefaultThemeMode: _enumValue(
      map,
      'ownerDefaultThemeMode',
      ThemeModeSetting.values,
      (value) => value.wireValue,
    ),
    ownerDefaultFontSizePreset: _enumValue(
      map,
      'ownerDefaultFontSizePreset',
      FontSizePreset.values,
      (value) => value.wireValue,
    ),
    hasSubAccountOverride: _bool(map, 'hasSubAccountOverride'),
    version: _nonNegativeInt(map, 'version'),
    updatedAt: _timestamp(map, 'updatedAt'),
  );
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$label must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$label keys must be strings');
    }
    result[key] = entry.value;
  }
  return result;
}

void _only(Map<String, Object?> map, Set<String> allowed) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('unexpected key: $key');
    }
  }
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

int _nonNegativeInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value < 0) {
    throw FormatException('$key must be a non-negative integer');
  }
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) {
    throw FormatException('$key must be a boolean');
  }
  return value;
}

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('$key must be a string or null');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

QuietHoursTime? _optionalQuietHoursTime(Map<String, Object?> map, String key) {
  final value = _optionalString(map, key);
  return value == null ? null : QuietHoursTime.parse(value);
}

List<String> _stringList(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return const <String>[];
  if (value is! List<Object?>) {
    throw FormatException('$key must be a list');
  }
  final values = <String>[];
  for (final item in value) {
    if (item is! String) {
      throw FormatException('$key items must be strings');
    }
    values.add(item);
  }
  return List<String>.unmodifiable(_normalizeKeywords(values));
}

DateTime _timestamp(Map<String, Object?> map, String key) {
  final raw = _string(map, key);
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$key must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

T _enumValue<T>(
  Map<String, Object?> map,
  String key,
  Iterable<T> values,
  String Function(T value) wireValue,
) => _enumFromString(_string(map, key), key, values, wireValue);

T _enumFromString<T>(
  String raw,
  String key,
  Iterable<T> values,
  String Function(T value) wireValue,
) {
  for (final value in values) {
    if (wireValue(value) == raw) return value;
  }
  throw FormatException('$key contains an unknown enum value: $raw');
}

Object _nullableMutationWire<T extends Object>(
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

T? _applyNullableMutation<T extends Object>(
  T? current,
  NullableSettingMutation<T>? mutation,
) {
  if (mutation == null) return current;
  return mutation.clearsValue ? null : mutation.value;
}

List<String> _normalizeKeywords(Iterable<String> values) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty || !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return result;
}

String _normalizeRingtoneId(String value) {
  final normalized = value.trim();
  if (normalized.length > 64 || !normalized.startsWith('official.')) {
    throw ArgumentError.value(
      value,
      'value',
      'ringtone id must use the official namespace',
    );
  }
  return normalized;
}
