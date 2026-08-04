import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaUserSettingsFacet
    implements UserSettingsCommandWriter, UserSettingsQueryReader {
  AlphaUserSettingsFacet({
    String userId = 'alpha-user',
    DateTime Function()? now,
    DateTime? initialUpdatedAt,
  }) : _userId = userId.trim(),
       _now = now ?? _utcNow,
       _aggregateUpdatedAt = (initialUpdatedAt ?? DateTime.utc(2026)).toUtc(),
       _appearanceUpdatedAt = (initialUpdatedAt ?? DateTime.utc(2026)).toUtc() {
    if (_userId.isEmpty) {
      throw ArgumentError.value(userId, 'userId', 'must not be empty');
    }
  }

  final String _userId;
  final DateTime Function() _now;
  bool _enablePush = true;
  bool _enableMarketing = false;
  String? _quietHoursStart;
  String? _quietHoursEnd;
  bool _allowStrangerMsg = true;
  ProfileVisibility _profileVisibility = ProfileVisibility.public;
  String? _contentLanguage;
  String? _feedPreference;
  bool _assistantEnabled = true;
  final List<String> _blockedKeywords = <String>[];
  String? _ringtoneId = 'official.default';
  bool _allowCallerRingtoneOverride = true;
  bool _enableCallVibration = true;
  bool _enableGroupCallRing = true;
  ThemeModeSetting _ownerThemeMode = ThemeModeSetting.system;
  FontSizePreset _ownerFontSizePreset = FontSizePreset.md;
  ThemeModeSetting? _personaThemeMode;
  FontSizePreset? _personaFontSizePreset;
  int _aggregateVersion = 1;
  int _appearanceVersion = 1;
  DateTime _aggregateUpdatedAt;
  DateTime _appearanceUpdatedAt;

  @override
  Future<NotificationSettingsView> getNotificationSettings() async =>
      NotificationSettingsView(
        userId: _userId,
        enablePush: _enablePush,
        enableMarketing: _enableMarketing,
        quietHoursStart: _quietHoursStart,
        quietHoursEnd: _quietHoursEnd,
        version: _aggregateVersion,
        updatedAt: _aggregateUpdatedAt,
      );

  @override
  Future<PrivacySettingsView> getPrivacySettings() async => PrivacySettingsView(
    userId: _userId,
    allowStrangerMsg: _allowStrangerMsg,
    profileVisibility: _profileVisibility.wireName,
    contentLanguage: _contentLanguage,
    feedPreference: _feedPreference,
    assistantEnabled: _assistantEnabled,
    blockedKeywords: _blockedKeywords,
    version: _aggregateVersion,
    updatedAt: _aggregateUpdatedAt,
  );

  @override
  Future<CallSettingsView> getCallSettings() async => CallSettingsView(
    userId: _userId,
    defaultIncomingCallRingtoneId: _ringtoneId,
    allowCallerRingtoneOverride: _allowCallerRingtoneOverride,
    enableCallVibration: _enableCallVibration,
    enableGroupCallRing: _enableGroupCallRing,
    version: _aggregateVersion,
    updatedAt: _aggregateUpdatedAt,
  );

  @override
  Future<AppearanceSettingsView> getAppearanceSettings() async => _appearance();

  @override
  Future<UserSettingsCommandResult> updateNotificationSettings(
    UpdateNotificationSettingsCommand command,
  ) async {
    final nextQuietHoursStart = _nextNullable(
      _quietHoursStart,
      command.quietHoursStart,
    );
    final nextQuietHoursEnd = _nextNullable(
      _quietHoursEnd,
      command.quietHoursEnd,
    );
    final changed =
        (command.enablePush != null && command.enablePush != _enablePush) ||
        (command.enableMarketing != null &&
            command.enableMarketing != _enableMarketing) ||
        nextQuietHoursStart != _quietHoursStart ||
        nextQuietHoursEnd != _quietHoursEnd;
    _enablePush = command.enablePush ?? _enablePush;
    _enableMarketing = command.enableMarketing ?? _enableMarketing;
    _quietHoursStart = nextQuietHoursStart;
    _quietHoursEnd = nextQuietHoursEnd;
    return _commitAggregate(changed);
  }

  @override
  Future<UserSettingsCommandResult> updatePrivacySettings(
    UpdatePrivacySettingsCommand command,
  ) async {
    final nextKeywords = command.blockedKeywords ?? _blockedKeywords;
    final changed =
        (command.allowStrangerMsg != null &&
            command.allowStrangerMsg != _allowStrangerMsg) ||
        (command.profileVisibility != null &&
            command.profileVisibility != _profileVisibility) ||
        (command.assistantEnabled != null &&
            command.assistantEnabled != _assistantEnabled) ||
        !_same(_blockedKeywords, nextKeywords);
    _allowStrangerMsg = command.allowStrangerMsg ?? _allowStrangerMsg;
    _profileVisibility = command.profileVisibility ?? _profileVisibility;
    _assistantEnabled = command.assistantEnabled ?? _assistantEnabled;
    if (command.blockedKeywords != null) {
      _blockedKeywords
        ..clear()
        ..addAll(command.blockedKeywords!);
    }
    return _commitAggregate(changed);
  }

  @override
  Future<UserSettingsCommandResult> updateCallSettings(
    UpdateCallSettingsCommand command,
  ) async {
    final nextRingtone = _nextNullable(
      _ringtoneId,
      command.defaultIncomingCallRingtoneId,
    );
    final changed =
        nextRingtone != _ringtoneId ||
        (command.allowCallerRingtoneOverride != null &&
            command.allowCallerRingtoneOverride !=
                _allowCallerRingtoneOverride) ||
        (command.enableCallVibration != null &&
            command.enableCallVibration != _enableCallVibration) ||
        (command.enableGroupCallRing != null &&
            command.enableGroupCallRing != _enableGroupCallRing);
    _ringtoneId = nextRingtone;
    _allowCallerRingtoneOverride =
        command.allowCallerRingtoneOverride ?? _allowCallerRingtoneOverride;
    _enableCallVibration = command.enableCallVibration ?? _enableCallVibration;
    _enableGroupCallRing = command.enableGroupCallRing ?? _enableGroupCallRing;
    return _commitAggregate(changed);
  }

  @override
  Future<AppearanceSettingsView> updateAppearanceSettings(
    UpdateAppearanceSettingsCommand command,
  ) async {
    var aggregateChanged = false;
    final changed = switch (command.applyScope) {
      AppearanceApplyScope.allAccounts => _applyOwnerAppearance(command),
      AppearanceApplyScope.currentPersona => _applyPersonaAppearance(command),
      AppearanceApplyScope.inheritOwnerDefault => _clearPersonaAppearance(),
    };
    if (command.applyScope == AppearanceApplyScope.allAccounts) {
      aggregateChanged =
          _ownerThemeMode != command.themeMode ||
          _ownerFontSizePreset != command.fontSizePreset;
      _ownerThemeMode = command.themeMode;
      _ownerFontSizePreset = command.fontSizePreset;
    }
    if (changed) {
      final changedAt = _now().toUtc();
      _appearanceVersion++;
      _appearanceUpdatedAt = changedAt;
      if (aggregateChanged) {
        _aggregateVersion++;
        _aggregateUpdatedAt = changedAt;
      }
    }
    return _appearance();
  }

  bool _applyOwnerAppearance(UpdateAppearanceSettingsCommand command) {
    final changed =
        _ownerThemeMode != command.themeMode ||
        _ownerFontSizePreset != command.fontSizePreset ||
        _personaThemeMode != null ||
        _personaFontSizePreset != null;
    _personaThemeMode = null;
    _personaFontSizePreset = null;
    return changed;
  }

  bool _applyPersonaAppearance(UpdateAppearanceSettingsCommand command) {
    final changed =
        _personaThemeMode != command.themeMode ||
        _personaFontSizePreset != command.fontSizePreset;
    _personaThemeMode = command.themeMode;
    _personaFontSizePreset = command.fontSizePreset;
    return changed;
  }

  bool _clearPersonaAppearance() {
    final changed = _personaThemeMode != null || _personaFontSizePreset != null;
    _personaThemeMode = null;
    _personaFontSizePreset = null;
    return changed;
  }

  UserSettingsCommandResult _commitAggregate(bool changed) {
    if (changed) {
      _aggregateVersion++;
      _aggregateUpdatedAt = _now().toUtc();
    }
    return UserSettingsCommandResult(
      userId: _userId,
      version: _aggregateVersion,
      idempotentReplay: !changed,
    );
  }

  AppearanceSettingsView _appearance() {
    final hasOverride =
        _personaThemeMode != null && _personaFontSizePreset != null;
    return AppearanceSettingsView(
      themeMode: (_personaThemeMode ?? _ownerThemeMode).wireName,
      fontSizePreset: (_personaFontSizePreset ?? _ownerFontSizePreset).wireName,
      source: hasOverride ? 'sub_override' : 'owner_default',
      ownerDefaultThemeMode: _ownerThemeMode.wireName,
      ownerDefaultFontSizePreset: _ownerFontSizePreset.wireName,
      hasPersonaOverride: hasOverride,
      version: _appearanceVersion,
      updatedAt: _appearanceUpdatedAt,
    );
  }

  T? _nextNullable<T extends Object>(T? current, T? mutation) {
    return mutation ?? current;
  }

  bool _same(List<String> left, List<String> right) {
    if (left.length != right.length) return false;
    for (var index = 0; index < left.length; index++) {
      if (left[index] != right[index]) return false;
    }
    return true;
  }

  static DateTime _utcNow() => DateTime.now().toUtc();
}

final class AlphaCredentialBindingWriter
    implements AppCredentialBindingCommandWriter, CredentialBindingQuery {
  final Map<CredentialType, _AlphaCredentialBindingState> _bindings =
      <CredentialType, _AlphaCredentialBindingState>{};

  @override
  Future<ListCredentialsSlice> listCredentials(
    ListCredentialsQuery query,
  ) async {
    final items =
        _bindings.values
            .map(
              (binding) => CredentialBindingView(
                id: binding.id,
                credentialType: binding.credentialType,
                displayLabel: binding.displayLabel,
                isActive: true,
                boundAt: binding.boundAt,
                version: binding.version,
              ),
            )
            .toList(growable: false)
          ..sort(
            (left, right) => left.credentialType.wireName.compareTo(
              right.credentialType.wireName,
            ),
          );
    return ListCredentialsSlice(credentials: items);
  }

  @override
  Future<CredentialBindingCommandResult> bindPhoneCredential(
    BindPhoneCredentialCommand command,
  ) => _bind(
    CredentialType.phone,
    command.displayLabel ?? _maskPhoneCredential(command.phone),
  );

  @override
  Future<AuthSessionGrant> completeFederatedPhoneBinding(
    CompleteFederatedPhoneBindingCommand command,
  ) async {
    return AuthSessionGrant(
      accessToken: 'alpha-binding-access',
      refreshToken: 'alpha-binding-refresh',
      ownerId: 'alpha-owner',
      accountState: 'active',
      identityOrigin: 'federated_phone',
      logicalShard: 0,
      anonymousRetentionPolicy: 'retained',
      personaCount: 1,
      sessionRememberTtlSeconds: 2592000,
      activePersona: const ActivePersonaEnvelope(
        personaId: 'alpha-persona-primary',
      ),
      accountHint: AccountHintSnapshot(
        displayName: 'Alpha Account',
        nicknameCustomized: false,
        avatarUrl: '',
        avatarAssetId: '',
        maskedPhone: _maskPhoneCredential(command.phone),
        identityOrigin: 'federated_phone',
      ),
    );
  }

  @override
  Future<CredentialBindingCommandResult> bindCarrierPhoneCredential(
    BindCarrierPhoneCredentialCommand command,
  ) =>
      _bind(CredentialType.carrierPhone, command.displayLabel ?? '138****0000');

  @override
  Future<CredentialBindingCommandResult> unbindCredential(
    UnbindCredentialCommand command,
  ) async {
    final credentialType = CredentialType.fromWire(
      command.credentialType,
      'UnbindCredentialCommand.credentialType',
    );
    final existing = _bindings[credentialType];
    if (existing == null) {
      throw StateError('credential binding not found');
    }
    if (_bindings.length == 1) {
      throw StateError('the last credential binding cannot be removed');
    }
    _bindings.remove(credentialType);
    return CredentialBindingCommandResult(
      credentialType: credentialType,
      isActive: false,
      version: existing.version + 1,
      idempotentReplay: false,
      displayLabel: existing.displayLabel,
    );
  }

  Future<CredentialBindingCommandResult> _bind(
    CredentialType type,
    String label,
  ) async {
    final existing = _bindings[type];
    if (existing != null) {
      return CredentialBindingCommandResult(
        credentialType: existing.credentialType,
        isActive: true,
        version: existing.version,
        idempotentReplay: true,
        displayLabel: existing.displayLabel,
      );
    }
    final binding = _AlphaCredentialBindingState(
      id: 'alpha-credential-${type.wireName}',
      credentialType: type,
      version: 1,
      displayLabel: label,
      boundAt: DateTime.now().toUtc(),
    );
    _bindings[type] = binding;
    return CredentialBindingCommandResult(
      credentialType: type,
      isActive: true,
      version: binding.version,
      idempotentReplay: false,
      displayLabel: binding.displayLabel,
    );
  }
}

final class _AlphaCredentialBindingState {
  const _AlphaCredentialBindingState({
    required this.id,
    required this.credentialType,
    required this.displayLabel,
    required this.boundAt,
    required this.version,
  });

  final String id;
  final CredentialType credentialType;
  final String displayLabel;
  final DateTime boundAt;
  final int version;
}

final class AlphaProfileCommandWriter implements ProfileCommandWriter {
  int _version = 1;

  @override
  Future<ProfileUpdateSnapshot> updateUserProfile(
    UpdateUserProfileCommand command,
  ) async {
    _version++;
    return ProfileUpdateSnapshot(
      userId: 'alpha-user',
      nickname: command.nickname ?? command.displayName ?? 'Alpha 用户',
      nicknameCustomized:
          command.nickname != null || command.displayName != null,
      profileVersion: _version,
      avatarVersion: _version,
      avatarUrl: command.avatarUrl,
      avatarAssetId: command.avatarAssetId,
      backgroundUrl: command.backgroundUrl,
      backgroundAssetId: command.backgroundAssetId,
      bio: command.bio,
      identityTags:
          command.identityTags ??
          <String>[
            if (command.occupationTagRef != null) command.occupationTagRef!,
            ...?command.interestTagRefs,
          ],
      gender: command.gender,
      birthDate: _parseOptionalDate(command.birthDate),
      regionTagRef: command.regionTagRef,
      updatedAt: DateTime.now().toUtc(),
    );
  }
}

DateTime? _parseOptionalDate(String? value) {
  if (value == null) return null;
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw ArgumentError.value(value, 'birthDate', 'must be an ISO-8601 date');
  }
  return parsed.toUtc();
}

String _maskPhoneCredential(String phone) {
  final normalized = phone.trim();
  if (normalized.length < 7) return '***';
  return '${normalized.substring(0, 3)}****'
      '${normalized.substring(normalized.length - 4)}';
}
