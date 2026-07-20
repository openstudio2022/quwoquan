import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

/// 设置中枢「通知与提醒 / 通话与铃声」区块状态：
/// 读投影为单一真相源；toggle 乐观更新，命令失败回滚并暴露结构化错误。
class UserSettingsSectionsState {
  const UserSettingsSectionsState({
    this.notification,
    this.privacy,
    this.call,
    this.isLoading = false,
    this.rawError,
  });

  final contracts.NotificationSettingsView? notification;
  final contracts.PrivacySettingsView? privacy;
  final contracts.CallSettingsView? call;
  final bool isLoading;
  final Object? rawError;

  bool get isLoaded => notification != null && privacy != null && call != null;

  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  UserSettingsSectionsState copyWith({
    contracts.NotificationSettingsView? notification,
    contracts.PrivacySettingsView? privacy,
    contracts.CallSettingsView? call,
    bool? isLoading,
    Object? Function()? rawError,
  }) {
    return UserSettingsSectionsState(
      notification: notification ?? this.notification,
      privacy: privacy ?? this.privacy,
      call: call ?? this.call,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}

class UserSettingsSectionsNotifier extends Notifier<UserSettingsSectionsState> {
  contracts.UserSettingsQueryReader get _reader =>
      ref.read(userSettingsQueryReaderProvider);

  contracts.UserSettingsCommandWriter get _commands =>
      ref.read(userSettingsCommandWriterProvider);

  @override
  UserSettingsSectionsState build() {
    return const UserSettingsSectionsState();
  }

  Future<void> load() async {
    if (state.isLoading) {
      return;
    }
    state = state.copyWith(isLoading: true, rawError: () => null);
    try {
      final results = await Future.wait(<Future<Object>>[
        _reader.getNotificationSettings(),
        _reader.getPrivacySettings(),
        _reader.getCallSettings(),
      ]);
      state = state.copyWith(
        notification: results[0] as contracts.NotificationSettingsView,
        privacy: results[1] as contracts.PrivacySettingsView,
        call: results[2] as contracts.CallSettingsView,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }

  Future<bool> setEnablePush(bool value) {
    final previous = state.notification;
    if (previous == null) {
      return Future<bool>.value(false);
    }
    return _mutate(
      optimistic: () => state = state.copyWith(
        notification: previous.copyWith(enablePush: value),
      ),
      rollback: () => state = state.copyWith(notification: previous),
      command: () => _commands.updateNotificationSettings(
        contracts.UpdateNotificationSettingsCommand(enablePush: value),
      ),
    );
  }

  Future<bool> setEnableMarketing(bool value) {
    final previous = state.notification;
    if (previous == null) {
      return Future<bool>.value(false);
    }
    return _mutate(
      optimistic: () => state = state.copyWith(
        notification: previous.copyWith(enableMarketing: value),
      ),
      rollback: () => state = state.copyWith(notification: previous),
      command: () => _commands.updateNotificationSettings(
        contracts.UpdateNotificationSettingsCommand(enableMarketing: value),
      ),
    );
  }

  Future<bool> setAllowCallerRingtoneOverride(bool value) {
    final previous = state.call;
    if (previous == null) {
      return Future<bool>.value(false);
    }
    return _mutate(
      optimistic: () => state = state.copyWith(
        call: previous.copyWith(allowCallerRingtoneOverride: value),
      ),
      rollback: () => state = state.copyWith(call: previous),
      command: () => _commands.updateCallSettings(
        contracts.UpdateCallSettingsCommand(allowCallerRingtoneOverride: value),
      ),
    );
  }

  Future<bool> setAllowStrangerMsg(bool value) {
    final previous = state.privacy;
    if (previous == null) return Future<bool>.value(false);
    return _mutate(
      optimistic: () => state = state.copyWith(
        privacy: previous.copyWith(allowStrangerMsg: value),
      ),
      rollback: () => state = state.copyWith(privacy: previous),
      command: () => _commands.updatePrivacySettings(
        contracts.UpdatePrivacySettingsCommand(allowStrangerMsg: value),
      ),
    );
  }

  Future<bool> setProfileVisibility(contracts.ProfileVisibility value) {
    final previous = state.privacy;
    if (previous == null) return Future<bool>.value(false);
    return _mutate(
      optimistic: () => state = state.copyWith(
        privacy: previous.copyWith(profileVisibility: value),
      ),
      rollback: () => state = state.copyWith(privacy: previous),
      command: () => _commands.updatePrivacySettings(
        contracts.UpdatePrivacySettingsCommand(profileVisibility: value),
      ),
    );
  }

  Future<bool> setAssistantEnabled(bool value) {
    final previous = state.privacy;
    if (previous == null) return Future<bool>.value(false);
    return _mutate(
      optimistic: () => state = state.copyWith(
        privacy: previous.copyWith(assistantEnabled: value),
      ),
      rollback: () => state = state.copyWith(privacy: previous),
      command: () => _commands.updatePrivacySettings(
        contracts.UpdatePrivacySettingsCommand(assistantEnabled: value),
      ),
    );
  }

  Future<bool> setDefaultRingtone(contracts.OfficialRingtoneId ringtoneId) {
    final previous = state.call;
    if (previous == null) return Future<bool>.value(false);
    return _mutate(
      optimistic: () => state = state.copyWith(
        call: previous.copyWith(
          defaultIncomingCallRingtoneId:
              contracts.NullableSettingMutation<
                contracts.OfficialRingtoneId
              >.set(ringtoneId),
        ),
      ),
      rollback: () => state = state.copyWith(call: previous),
      command: () => _commands.updateCallSettings(
        contracts.UpdateCallSettingsCommand(
          defaultIncomingCallRingtoneId:
              contracts.NullableSettingMutation<
                contracts.OfficialRingtoneId
              >.set(ringtoneId),
        ),
      ),
    );
  }

  Future<bool> setEnableCallVibration(bool value) {
    final previous = state.call;
    if (previous == null) {
      return Future<bool>.value(false);
    }
    return _mutate(
      optimistic: () => state = state.copyWith(
        call: previous.copyWith(enableCallVibration: value),
      ),
      rollback: () => state = state.copyWith(call: previous),
      command: () => _commands.updateCallSettings(
        contracts.UpdateCallSettingsCommand(enableCallVibration: value),
      ),
    );
  }

  Future<bool> setEnableGroupCallRing(bool value) {
    final previous = state.call;
    if (previous == null) {
      return Future<bool>.value(false);
    }
    return _mutate(
      optimistic: () => state = state.copyWith(
        call: previous.copyWith(enableGroupCallRing: value),
      ),
      rollback: () => state = state.copyWith(call: previous),
      command: () => _commands.updateCallSettings(
        contracts.UpdateCallSettingsCommand(enableGroupCallRing: value),
      ),
    );
  }

  Future<bool> _mutate({
    required void Function() optimistic,
    required void Function() rollback,
    required Future<contracts.UserSettingsCommandResult> Function() command,
  }) async {
    optimistic();
    try {
      await command();
      state = state.copyWith(rawError: () => null);
      return true;
    } catch (e) {
      rollback();
      state = state.copyWith(rawError: () => e);
      return false;
    }
  }
}

final userSettingsSectionsProvider =
    NotifierProvider<UserSettingsSectionsNotifier, UserSettingsSectionsState>(
      UserSettingsSectionsNotifier.new,
    );
