import 'user_operation_contracts.g.dart';

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

abstract interface class UserSettingsQueryReader {
  Future<NotificationSettingsView> getNotificationSettings();
  Future<PrivacySettingsView> getPrivacySettings();
  Future<CallSettingsView> getCallSettings();
  Future<AppearanceSettingsView> getAppearanceSettings();
}
