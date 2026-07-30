import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef UserSettingsInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// UserSettings 四个 GET 的 production generated-client adapter。
final class RemoteUserSettingsQueryReader implements UserSettingsQueryReader {
  const RemoteUserSettingsQueryReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final UserSettingsInvocationContextFactory invocationContext;

  @override
  Future<NotificationSettingsView> getNotificationSettings() =>
      client.userUserSettingsGetNotificationSettings(
        UserSettingsQuery(),
        context: invocationContext(UserRequestPageIds.getNotificationSettings),
      );

  @override
  Future<PrivacySettingsView> getPrivacySettings() =>
      client.userUserSettingsGetPrivacySettings(
        UserSettingsQuery(),
        context: invocationContext(UserRequestPageIds.getPrivacySettings),
      );

  @override
  Future<CallSettingsView> getCallSettings() =>
      client.userUserSettingsGetCallSettings(
        UserSettingsQuery(),
        context: invocationContext(UserRequestPageIds.getCallSettings),
      );

  @override
  Future<AppearanceSettingsView> getAppearanceSettings() =>
      client.userUserSettingsGetAppearanceSettings(
        UserSettingsQuery(),
        context: invocationContext(UserRequestPageIds.getAppearanceSettings),
      );
}

/// UserSettings 的 production generated-client adapter。
final class RemoteUserSettingsCommandWriter
    implements UserSettingsCommandWriter {
  const RemoteUserSettingsCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final UserSettingsInvocationContextFactory invocationContext;

  @override
  Future<UserSettingsCommandResult> updateNotificationSettings(
    UpdateNotificationSettingsCommand command,
  ) => client.userUserSettingsUpdateNotificationSettings(
    command,
    context: invocationContext(UserRequestPageIds.updateNotificationSettings),
  );

  @override
  Future<UserSettingsCommandResult> updatePrivacySettings(
    UpdatePrivacySettingsCommand command,
  ) => client.userUserSettingsUpdatePrivacySettings(
    command,
    context: invocationContext(UserRequestPageIds.updatePrivacySettings),
  );

  @override
  Future<UserSettingsCommandResult> updateCallSettings(
    UpdateCallSettingsCommand command,
  ) => client.userUserSettingsUpdateCallSettings(
    command,
    context: invocationContext(UserRequestPageIds.updateCallSettings),
  );

  @override
  Future<AppearanceSettingsView> updateAppearanceSettings(
    UpdateAppearanceSettingsCommand command,
  ) => client.userUserSettingsUpdateAppearanceSettings(
    command,
    context: invocationContext(UserRequestPageIds.updateAppearanceSettings),
  );
}
