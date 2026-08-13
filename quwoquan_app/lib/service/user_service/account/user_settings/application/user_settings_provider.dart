import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

/// 设置中枢「通知与提醒 / 通话与铃声」区块状态：
/// 读投影为单一真相源；toggle 乐观更新，命令失败回滚并暴露结构化错误。
///
/// [rawError] 只承载**加载**失败（触发整页错误态）；单个开关命令失败进入
/// [actionError]（回滚 + dialog 轻反馈），不得把动作失败升级为整页错误、
/// 清空用户正在操作的行区。
class UserSettingsSectionsState {
  const UserSettingsSectionsState({
    this.notification,
    this.privacy,
    this.call,
    this.isLoading = false,
    this.rawError,
    this.actionError,
  });

  final contracts.NotificationSettingsView? notification;
  final contracts.PrivacySettingsView? privacy;
  final contracts.CallSettingsView? call;
  final bool isLoading;
  final Object? rawError;
  final Object? actionError;

  bool get isLoaded => notification != null && privacy != null && call != null;

  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  UserSettingsSectionsState copyWith({
    contracts.NotificationSettingsView? notification,
    contracts.PrivacySettingsView? privacy,
    contracts.CallSettingsView? call,
    bool? isLoading,
    Object? Function()? rawError,
    Object? Function()? actionError,
  }) {
    return UserSettingsSectionsState(
      notification: notification ?? this.notification,
      privacy: privacy ?? this.privacy,
      call: call ?? this.call,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
      actionError: actionError != null ? actionError() : this.actionError,
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
        notification: _copyNotification(previous, enablePush: value),
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
        notification: _copyNotification(previous, enableMarketing: value),
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
        call: _copyCall(previous, allowCallerRingtoneOverride: value),
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
        privacy: _copyPrivacy(previous, allowStrangerMsg: value),
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
        privacy: _copyPrivacy(previous, profileVisibility: value),
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
        privacy: _copyPrivacy(previous, assistantEnabled: value),
      ),
      rollback: () => state = state.copyWith(privacy: previous),
      command: () => _commands.updatePrivacySettings(
        contracts.UpdatePrivacySettingsCommand(assistantEnabled: value),
      ),
    );
  }

  Future<bool> setDefaultRingtone(String ringtoneId) {
    final previous = state.call;
    if (previous == null) return Future<bool>.value(false);
    return _mutate(
      optimistic: () => state = state.copyWith(
        call: _copyCall(previous, defaultIncomingCallRingtoneId: ringtoneId),
      ),
      rollback: () => state = state.copyWith(call: previous),
      command: () => _commands.updateCallSettings(
        contracts.UpdateCallSettingsCommand(
          defaultIncomingCallRingtoneId: ringtoneId,
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
        call: _copyCall(previous, enableCallVibration: value),
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
        call: _copyCall(previous, enableGroupCallRing: value),
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
      state = state.copyWith(actionError: () => null);
      return true;
    } catch (e) {
      rollback();
      // 动作失败只回滚 + 记录 actionError 供 dialog 消费；
      // 不污染 rawError，页面主体（行区）必须保持可用。
      state = state.copyWith(actionError: () => e);
      return false;
    }
  }
}

contracts.NotificationSettingsView _copyNotification(
  contracts.NotificationSettingsView value, {
  bool? enablePush,
  bool? enableMarketing,
}) => contracts.NotificationSettingsView(
  userId: value.userId,
  enablePush: enablePush ?? value.enablePush,
  enableMarketing: enableMarketing ?? value.enableMarketing,
  quietHoursStart: value.quietHoursStart,
  quietHoursEnd: value.quietHoursEnd,
  version: value.version,
  updatedAt: value.updatedAt,
);

contracts.PrivacySettingsView _copyPrivacy(
  contracts.PrivacySettingsView value, {
  bool? allowStrangerMsg,
  contracts.ProfileVisibility? profileVisibility,
  bool? assistantEnabled,
}) => contracts.PrivacySettingsView(
  userId: value.userId,
  allowStrangerMsg: allowStrangerMsg ?? value.allowStrangerMsg,
  profileVisibility: profileVisibility ?? value.profileVisibility,
  contentLanguage: value.contentLanguage,
  feedPreference: value.feedPreference,
  assistantEnabled: assistantEnabled ?? value.assistantEnabled,
  blockedKeywords: value.blockedKeywords,
  version: value.version,
  updatedAt: value.updatedAt,
);

contracts.CallSettingsView _copyCall(
  contracts.CallSettingsView value, {
  String? defaultIncomingCallRingtoneId,
  bool? allowCallerRingtoneOverride,
  bool? enableCallVibration,
  bool? enableGroupCallRing,
}) => contracts.CallSettingsView(
  userId: value.userId,
  defaultIncomingCallRingtoneId:
      defaultIncomingCallRingtoneId ?? value.defaultIncomingCallRingtoneId,
  allowCallerRingtoneOverride:
      allowCallerRingtoneOverride ?? value.allowCallerRingtoneOverride,
  enableCallVibration: enableCallVibration ?? value.enableCallVibration,
  enableGroupCallRing: enableGroupCallRing ?? value.enableGroupCallRing,
  version: value.version,
  updatedAt: value.updatedAt,
);

final userSettingsSectionsProvider =
    NotifierProvider<UserSettingsSectionsNotifier, UserSettingsSectionsState>(
      UserSettingsSectionsNotifier.new,
    );
