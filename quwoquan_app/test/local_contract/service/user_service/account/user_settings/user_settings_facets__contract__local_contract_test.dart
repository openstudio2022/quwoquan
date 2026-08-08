// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/notification-privacy-settings/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/appearance-accessibility-settings/spec.md#gwt-001
// readiness_case: user_settings_get_notification_settings_app_local
// readiness_case: user_settings_get_privacy_settings_app_local
// readiness_case: user_settings_get_call_settings_app_local
// readiness_case: user_settings_get_appearance_settings_app_local
// readiness_case: user_settings_update_notification_settings_app_local
// readiness_case: user_settings_update_privacy_settings_app_local
// readiness_case: user_settings_update_call_settings_app_local
// readiness_case: user_settings_update_appearance_settings_app_local
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/adapters/user_settings_remote.dart';
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
    expect(notification.quietHoursStart, '22:30');
    expect(notification.quietHoursEnd, '07:15');
    expect(notification.version, 0);
    expect(notification.updatedAt, DateTime.utc(2026, 7, 20));

    final privacy = decodePrivacySettingsView(<String, Object?>{
      'userId': 'user-1',
      'allowStrangerMsg': false,
      'profileVisibility': 'friends',
      'contentLanguage': 'zh-CN',
      'feedPreference': 'chronological',
      'assistantEnabled': true,
      'blockedKeywords': <Object?>['alpha', 'beta'],
      'version': 4,
      'updatedAt': '2026-07-20T00:01:00+00:00',
    });
    expect(privacy.profileVisibility, ProfileVisibility.friends);
    expect(privacy.feedPreference, FeedPreference.chronological);
    // 去重/裁剪是 UpdatePrivacySettingsCommand 声明的写入侧规范化，
    // 读取侧只忠实反映服务端已存值。
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
    expect(call.defaultIncomingCallRingtoneId, 'official.classic');
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
    expect(appearance.hasPersonaOverride, isTrue);
    expect(appearance.version, 7);
  });

  test('UserSettings typed commands encode only their declared fields', () {
    final notification =
        encodeUserUserSettingsUpdateNotificationSettingsGeneratedRequest(
          UpdateNotificationSettingsCommand(
            enablePush: false,
            enableMarketing: true,
            quietHoursStart: '23:05',
          ),
        );
    // 未设置的可空字段整体缺席，而不是编码成 null 或空串。
    expect(notification.body, <String, Object?>{
      'enablePush': false,
      'enableMarketing': true,
      'quietHoursStart': '23:05',
    });

    final privacy = encodeUserUserSettingsUpdatePrivacySettingsGeneratedRequest(
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

    final call = encodeUserUserSettingsUpdateCallSettingsGeneratedRequest(
      UpdateCallSettingsCommand(
        defaultIncomingCallRingtoneId: 'official.bell',
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

    final appearance =
        encodeUserUserSettingsUpdateAppearanceSettingsGeneratedRequest(
          UpdateAppearanceSettingsCommand(
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

      final notification = await query.getNotificationSettings();
      final privacy = await query.getPrivacySettings();
      final call = await query.getCallSettings();
      final appearance = await query.getAppearanceSettings();
      final notificationResult = await commands.updateNotificationSettings(
        UpdateNotificationSettingsCommand(enablePush: false),
      );
      final privacyResult = await commands.updatePrivacySettings(
        UpdatePrivacySettingsCommand(
          profileVisibility: ProfileVisibility.friends,
        ),
      );
      final callResult = await commands.updateCallSettings(
        UpdateCallSettingsCommand(enableCallVibration: false),
      );
      final appearanceResult = await commands.updateAppearanceSettings(
        UpdateAppearanceSettingsCommand(
          themeMode: ThemeModeSetting.light,
          fontSizePreset: FontSizePreset.md,
          applyScope: AppearanceApplyScope.allAccounts,
        ),
      );

      expect(notification.enablePush, isTrue);
      expect(privacy.profileVisibility, ProfileVisibility.public);
      expect(call.enableCallVibration, isTrue);
      expect(appearance.themeMode, ThemeModeSetting.system);
      expect(notificationResult.idempotentReplay, isFalse);
      expect(privacyResult.idempotentReplay, isFalse);
      expect(callResult.idempotentReplay, isFalse);
      expect(appearanceResult.themeMode, ThemeModeSetting.system);
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
      expect(executor.methods, <String>[
        'GET',
        'GET',
        'GET',
        'GET',
        'PATCH',
        'PATCH',
        'PATCH',
        'PATCH',
      ]);
      expect(executor.paths, <String>[
        '/user/settings/notifications',
        '/user/settings/privacy',
        '/user/settings/calls',
        '/user/settings/appearance',
        '/user/settings/notifications',
        '/user/settings/privacy',
        '/user/settings/calls',
        '/user/settings/appearance',
      ]);
      expect(
        executor.contexts,
        everyElement(
          isA<CloudOperationInvocationContext>().having(
            (context) => context.actor.accountId,
            'actor.accountId',
            'account-1',
          ),
        ),
      );
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

  test('UserSettings 八个 Remote operation 均原样透传 canonical failure', () async {
    final failure = CloudErrorMapper.fromStatusCode(
      401,
      requestPath: '/user/settings',
    );
    final client = GeneratedCloudOperationClient(_FailingExecutor(failure));
    final query = RemoteUserSettingsQueryReader(
      client: client,
      invocationContext: _context,
    );
    final commands = RemoteUserSettingsCommandWriter(
      client: client,
      invocationContext: _context,
    );
    final operations = <Future<Object?> Function()>[
      query.getNotificationSettings,
      query.getPrivacySettings,
      query.getCallSettings,
      query.getAppearanceSettings,
      () => commands.updateNotificationSettings(
        UpdateNotificationSettingsCommand(enablePush: false),
      ),
      () => commands.updatePrivacySettings(
        UpdatePrivacySettingsCommand(
          profileVisibility: ProfileVisibility.friends,
        ),
      ),
      () => commands.updateCallSettings(
        UpdateCallSettingsCommand(enableCallVibration: false),
      ),
      () => commands.updateAppearanceSettings(
        UpdateAppearanceSettingsCommand(
          themeMode: ThemeModeSetting.light,
          fontSizePreset: FontSizePreset.md,
          applyScope: AppearanceApplyScope.allAccounts,
        ),
      ),
    ];

    for (final operation in operations) {
      await expectLater(operation(), throwsA(same(failure)));
    }
  });

  test('UserSettings decoders fail closed on drifted fields and enums', () {
    expect(
      () => decodePrivacySettingsView(
        _privacyResponse()
          ..['profileVisibility'] = 'retired'
          ..['retiredAlias'] = true,
      ),
      throwsFormatException,
    );
    expect(
      () => decodeNotificationSettingsView(
        _notificationResponse()..['quietHoursStart'] = '25:00',
      ),
      throwsFormatException,
    );
    // 铃声是否属于官方库由服务端 USER.SETTING.invalid_call_ringtone 判定，
    // 解码层只保证 wire 形状，不复制该业务规则。
    expect(
      () => decodeNotificationSettingsView(
        _notificationResponse()..['quietHoursEnd'] = '7:15',
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
      actor: const CloudOperationActorContext(
        accountId: 'account-1',
        personaId: 'persona-1',
      ),
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
  'hasPersonaOverride': hasOverride,
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
  final List<String> methods = <String>[];
  final List<String> paths = <String>[];
  final List<CloudOperationInvocationContext> contexts =
      <CloudOperationInvocationContext>[];
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
    methods.add(operation.method);
    paths.add(operation.pathTemplate);
    contexts.add(context);
    bodies.add(payload.body);
    return responseDecoder(responses[operation.canonicalOperationId]);
  }
}

final class _FailingExecutor implements CloudOperationExecutor {
  const _FailingExecutor(this.failure);

  final Object failure;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) => Future<TResponse>.error(failure);
}
