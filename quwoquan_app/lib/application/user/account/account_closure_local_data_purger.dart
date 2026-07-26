// ignore_for_file: prefer_initializing_formals

/// 云侧账号进入不可逆 closed 终态后，本机隐私数据的唯一清理编排。
final class AccountClosureLocalDataPurger {
  const AccountClosureLocalDataPurger({
    required Future<void> Function() clearBehaviorQueue,
    required Future<void> Function() clearTelemetryQueue,
    required Future<void> Function() clearRebuildableUserData,
    required Future<void> Function() purgePushAndIncomingCallState,
    required Future<void> Function() clearDraftsAndAccountPreferences,
  }) : _clearBehaviorQueue = clearBehaviorQueue,
       _clearTelemetryQueue = clearTelemetryQueue,
       _clearRebuildableUserData = clearRebuildableUserData,
       _purgePushAndIncomingCallState = purgePushAndIncomingCallState,
       _clearDraftsAndAccountPreferences = clearDraftsAndAccountPreferences;

  final Future<void> Function() _clearBehaviorQueue;
  final Future<void> Function() _clearTelemetryQueue;
  final Future<void> Function() _clearRebuildableUserData;
  final Future<void> Function() _purgePushAndIncomingCallState;
  final Future<void> Function() _clearDraftsAndAccountPreferences;

  /// 五个清理面全部启动；任一失败则把失败交给调用方记录，但不会跳过其他面。
  Future<void> purge() {
    return Future.wait<void>(<Future<void>>[
      Future<void>.sync(_clearBehaviorQueue),
      Future<void>.sync(_clearTelemetryQueue),
      Future<void>.sync(_clearRebuildableUserData),
      Future<void>.sync(_purgePushAndIncomingCallState),
      Future<void>.sync(_clearDraftsAndAccountPreferences),
    ]);
  }
}
