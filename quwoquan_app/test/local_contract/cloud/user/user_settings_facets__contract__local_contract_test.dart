import 'package:quwoquan_app/cloud/remote/user/user_settings/user_settings_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:test/test.dart';

void main() {
  test('UserSettings codecs cover every typed section field', () {
    final notification = decodeNotificationSettingsView(<String, Object?>{
      'userId': 'user-1',
      'enablePush': true,
      'enableMarketing': false,
      'quietHoursStart': '22:30',
      'quietHoursEnd': '07:15',
      'version': 0,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
    expect(notification.quietHoursStart, QuietHoursTime(hour: 22, minute: 30));
    expect(notification.quietHoursEnd, QuietHoursTime(hour: 7, minute: 15));
    expect(notification.version, 0);
    expect(notification.updatedAt, DateTime.utc(2026, 7, 20));

    final privacy = decodePrivacySettingsView(<String, Object?>{
      'userId': 'user-1',
      'allowStrangerMsg': false,
      'profileVisibility': 'friends',
      'contentLanguage': 'zh-CN',
      'feedPreference': 'chronological',
      'assistantEnabled': true,
      'blockedKeywords': <Object?>['alpha', ' beta ', 'alpha'],
      'version': 4,
      'updatedAt': '2026-07-20T00:01:00+00:00',
    });
    expect(privacy.profileVisibility, ProfileVisibility.friends);
    expect(privacy.feedPreference, FeedPreference.chronological);
    expect(privacy.blockedKeywords, <String>['alpha', 'beta']);

    final call = decodeCallSettingsView(<String, Object?>{
      'userId': 'user-1',
      'defaultIncomingCallRingtoneId': 'official.classic',
      'allowCallerRingtoneOverride': false,
      'enableCallVibration': true,
      'enableGroupCallRing': false,
      'version': 5,
      'updatedAt': '2026-07-20T00:02:00Z',
    });
    expect(call.defaultIncomingCallRingtoneId?.wireValue, 'official.classic');
    expect(call.allowCallerRingtoneOverride, isFalse);
    expect(call.enableCallVibration, isTrue);
    expect(call.enableGroupCallRing, isFalse);

    final appearance = decodeAppearanceSettingsView(
      _appearanceResponse(
        themeMode: 'dark',
        fontSizePreset: 'xl',
        source: 'sub_override',
        ownerThemeMode: 'light',
        ownerFontSizePreset: 'md',
        hasOverride: true,
        version: 7,
      ),
    );
    expect(appearance.themeMode, ThemeModeSetting.dark);
    expect(appearance.fontSizePreset, FontSizePreset.xl);
    expect(appearance.source, AppearanceSource.subOverride);
    expect(appearance.ownerDefaultThemeMode, ThemeModeSetting.light);
    expect(appearance.ownerDefaultFontSizePreset, FontSizePreset.md);
    expect(appearance.hasSubAccountOverride, isTrue);
    expect(appearance.version, 7);
  });

  test('UserSettings typed commands encode only their declared fields', () {
    final notification = encodeUpdateNotificationSettingsCommand(
      UpdateNotificationSettingsCommand(
        enablePush: false,
        enableMarketing: true,
        quietHoursStart: NullableSettingMutation<QuietHoursTime>.set(
          QuietHoursTime(hour: 23, minute: 5),
        ),
        quietHoursEnd: const NullableSettingMutation<QuietHoursTime>.clear(),
      ),
    );
    expect(notification.body, <String, Object?>{
      'enablePush': false,
      'enableMarketing': true,
      'quietHoursStart': '23:05',
      'quietHoursEnd': '',
    });

    final privacy = encodeUpdatePrivacySettingsCommand(
      UpdatePrivacySettingsCommand(
        allowStrangerMsg: false,
        profileVisibility: ProfileVisibility.privateProfile,
        blockedKeywords: const <String>[' alpha ', 'beta', 'alpha'],
        assistantEnabled: false,
      ),
    );
    expect(privacy.body, <String, Object?>{
      'allowStrangerMsg': false,
      'profileVisibility': 'private',
      'blockedKeywords': <String>['alpha', 'beta'],
      'assistantEnabled': false,
    });

    final call = encodeUpdateCallSettingsCommand(
      UpdateCallSettingsCommand(
        defaultIncomingCallRingtoneId:
            NullableSettingMutation<OfficialRingtoneId>.set(
              OfficialRingtoneId('official.bell'),
            ),
        allowCallerRingtoneOverride: true,
        enableCallVibration: false,
        enableGroupCallRing: true,
      ),
    );
    expect(call.body, <String, Object?>{
      'defaultIncomingCallRingtoneId': 'official.bell',
      'allowCallerRingtoneOverride': true,
      'enableCallVibration': false,
      'enableGroupCallRing': true,
    });

    final appearance = encodeUpdateAppearanceSettingsCommand(
      const UpdateAppearanceSettingsCommand(
        themeMode: ThemeModeSetting.dark,
        fontSizePreset: FontSizePreset.lg,
        applyScope: AppearanceApplyScope.inheritOwnerDefault,
      ),
    );
    expect(appearance.body, <String, Object?>{
      'themeMode': 'dark',
      'fontSizePreset': 'lg',
      'applyScope': 'inherit_owner_default',
    });
  });

  test(
    'UserSettings Remote binds all eight generated object operations',
    () async {
      final executor = _RecordingExecutor(<String, Object?>{
        AppCloudOperationIds.userUserSettingsGetNotificationSettings:
            _notificationResponse(),
        AppCloudOperationIds.userUserSettingsGetPrivacySettings:
            _privacyResponse(),
        AppCloudOperationIds.userUserSettingsGetCallSettings: _callResponse(),
        AppCloudOperationIds.userUserSettingsGetAppearanceSettings:
            _appearanceResponse(),
        AppCloudOperationIds.userUserSettingsUpdateNotificationSettings:
            _commandResponse(),
        AppCloudOperationIds.userUserSettingsUpdatePrivacySettings:
            _commandResponse(),
        AppCloudOperationIds.userUserSettingsUpdateCallSettings:
            _commandResponse(),
        AppCloudOperationIds.userUserSettingsUpdateAppearanceSettings:
            _appearanceResponse(),
      });
      final client = GeneratedCloudOperationClient(executor);
      final query = RemoteUserSettingsQueryReader(
        client: client,
        invocationContext: _context,
      );
      final commands = RemoteUserSettingsCommandWriter(
        client: client,
        invocationContext: _context,
      );

      await query.getNotificationSettings();
      await query.getPrivacySettings();
      await query.getCallSettings();
      await query.getAppearanceSettings();
      await commands.updateNotificationSettings(
        const UpdateNotificationSettingsCommand(enablePush: false),
      );
      await commands.updatePrivacySettings(
        UpdatePrivacySettingsCommand(
          profileVisibility: ProfileVisibility.friends,
        ),
      );
      await commands.updateCallSettings(
        const UpdateCallSettingsCommand(enableCallVibration: false),
      );
      await commands.updateAppearanceSettings(
        const UpdateAppearanceSettingsCommand(
          themeMode: ThemeModeSetting.light,
          fontSizePreset: FontSizePreset.md,
          applyScope: AppearanceApplyScope.allAccounts,
        ),
      );

      expect(executor.operationIds, <String>[
        AppCloudOperationIds.userUserSettingsGetNotificationSettings,
        AppCloudOperationIds.userUserSettingsGetPrivacySettings,
        AppCloudOperationIds.userUserSettingsGetCallSettings,
        AppCloudOperationIds.userUserSettingsGetAppearanceSettings,
        AppCloudOperationIds.userUserSettingsUpdateNotificationSettings,
        AppCloudOperationIds.userUserSettingsUpdatePrivacySettings,
        AppCloudOperationIds.userUserSettingsUpdateCallSettings,
        AppCloudOperationIds.userUserSettingsUpdateAppearanceSettings,
      ]);
      expect(executor.bodies.take(4), everyElement(isNull));
      expect(executor.bodies[4], <String, Object?>{'enablePush': false});
      expect(executor.bodies[5], <String, Object?>{
        'profileVisibility': 'friends',
      });
      expect(executor.bodies[6], <String, Object?>{
        'enableCallVibration': false,
      });
      expect(executor.bodies[7], <String, Object?>{
        'themeMode': 'light',
        'fontSizePreset': 'md',
        'applyScope': 'all_accounts',
      });
    },
  );

  test('UserSettings decoders fail closed on drifted fields and enums', () {
    expect(
      () => decodePrivacySettingsView(
        _privacyResponse()
          ..['profileVisibility'] = 'legacy'
          ..['legacyAlias'] = true,
      ),
      throwsFormatException,
    );
    expect(
      () => decodeNotificationSettingsView(
        _notificationResponse()..['quietHoursStart'] = '25:00',
      ),
      throwsFormatException,
    );
    expect(
      () => decodeCallSettingsView(
        _callResponse()
          ..['defaultIncomingCallRingtoneId'] = 'user-uploaded.ringtone',
      ),
      throwsFormatException,
    );
    expect(
      () => decodeAppearanceSettingsView(
        _appearanceResponse()..remove('updatedAt'),
      ),
      throwsFormatException,
    );
  });
}

CloudOperationInvocationContext _context(String clientPageId) =>
    CloudOperationInvocationContext(
      surfaceId: 'settingsHome',
      clientPageId: clientPageId,
      actor: const CloudOperationActorContext(personaId: 'persona-1'),
    );

Map<String, Object?> _notificationResponse() => <String, Object?>{
  'userId': 'user-1',
  'enablePush': true,
  'enableMarketing': false,
  'quietHoursStart': null,
  'quietHoursEnd': null,
  'version': 1,
  'updatedAt': '2026-07-20T00:00:00Z',
};

Map<String, Object?> _privacyResponse() => <String, Object?>{
  'userId': 'user-1',
  'allowStrangerMsg': true,
  'profileVisibility': 'public',
  'contentLanguage': null,
  'feedPreference': null,
  'assistantEnabled': true,
  'blockedKeywords': <Object?>[],
  'version': 1,
  'updatedAt': '2026-07-20T00:00:00Z',
};

Map<String, Object?> _callResponse() => <String, Object?>{
  'userId': 'user-1',
  'defaultIncomingCallRingtoneId': null,
  'allowCallerRingtoneOverride': true,
  'enableCallVibration': true,
  'enableGroupCallRing': true,
  'version': 1,
  'updatedAt': '2026-07-20T00:00:00Z',
};

Map<String, Object?> _appearanceResponse({
  String themeMode = 'system',
  String fontSizePreset = 'md',
  String source = 'owner_default',
  String ownerThemeMode = 'system',
  String ownerFontSizePreset = 'md',
  bool hasOverride = false,
  int version = 1,
}) => <String, Object?>{
  'themeMode': themeMode,
  'fontSizePreset': fontSizePreset,
  'source': source,
  'ownerDefaultThemeMode': ownerThemeMode,
  'ownerDefaultFontSizePreset': ownerFontSizePreset,
  'hasSubAccountOverride': hasOverride,
  'version': version,
  'updatedAt': '2026-07-20T00:00:00Z',
};

Map<String, Object?> _commandResponse() => <String, Object?>{
  'userId': 'user-1',
  'version': 2,
  'idempotentReplay': false,
};

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor(this.responses);

  final Map<String, Object?> responses;
  final List<String> operationIds = <String>[];
  final List<Object?> bodies = <Object?>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final payload = requestEncoder();
    operationIds.add(operation.canonicalOperationId);
    bodies.add(payload.body);
    return responseDecoder(responses[operation.canonicalOperationId]);
  }
}
