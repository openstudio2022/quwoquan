import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/app/recovery/recovery_failure_reporter.dart';
import 'package:quwoquan_app/app/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/app/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';

final class StartupRecoveryController extends ChangeNotifier {
  StartupRecoveryController({
    RecoveryVersionClient? versionClient,
    AppRecoveryNativeBridge? nativeBridge,
    RecoverySnapshot initialSnapshot = const RecoverySnapshot.startupChecking(),
    this.onRuntimeReenter,
    this._visibleCheckBudget = const Duration(milliseconds: 1500),
    this.recoveryBaseUrl = '',
  }) : _versionClient = versionClient ?? RecoveryVersionClient(),
       _nativeBridge = nativeBridge ?? AppRecoveryNativeBridge(),
       _stateMachine = RecoveryStateMachine(initial: initialSnapshot);

  final RecoveryVersionClient _versionClient;
  final AppRecoveryNativeBridge _nativeBridge;
  final Duration _visibleCheckBudget;
  final String recoveryBaseUrl;
  final RecoveryStateMachine _stateMachine;
  final Future<void> Function()? onRuntimeReenter;

  Timer? _visibleCheckTimer;
  bool _started = false;
  bool _openingExternalTarget = false;
  bool _updateTargetOpened = false;
  AppRecoveryNativeContext? _nativeContext;

  RecoverySnapshot get snapshot => _stateMachine.snapshot;
  bool get openingExternalTarget => _openingExternalTarget;

  void start() {
    if (_started) return;
    _started = true;
    unawaited(RecoveryFailureReporter.instance.flush());
    if (snapshot.phase == RecoveryPhase.runtimeUnavailable) return;
    _startVersionCheck();
  }

  void _startVersionCheck() {
    _visibleCheckTimer?.cancel();
    _visibleCheckTimer = Timer(_visibleCheckBudget, () {
      if (_stateMachine.markVersionUnavailable()) {
        notifyListeners();
      }
    });
    unawaited(_checkVersion());
  }

  Future<void> reenterRuntime() async {
    if (!_stateMachine.beginRuntimeReentry()) return;
    notifyListeners();
    try {
      final action = onRuntimeReenter;
      if (action == null) throw StateError('runtime reentry is unavailable');
      await action();
    } catch (_) {
      markRuntimeReentryFailed();
    }
  }

  void markRuntimeReentryFailed() {
    if (!_stateMachine.failRuntimeReentry()) return;
    notifyListeners();
    _startVersionCheck();
  }

  Future<void> _checkVersion() async {
    try {
      final nativeContext = await _nativeBridge.context();
      if (nativeContext == null) return;
      _nativeContext = nativeContext;
      final result = await _versionClient.fetch(
        baseUrl: recoveryBaseUrl.trim().isEmpty
            ? nativeContext.recoveryBaseUrl
            : recoveryBaseUrl,
        platform: nativeContext.platform,
        appVersion: nativeContext.appVersion,
        buildNumber: nativeContext.buildNumber,
      );
      if (_stateMachine.confirmVersion(
        currentBuild: nativeContext.buildNumber,
        latestBuild: result.latestBuild,
        updateUrl: result.updateUrl,
        recoveryUrl: result.recoveryUrl,
      )) {
        _visibleCheckTimer?.cancel();
        notifyListeners();
      }
    } catch (_) {
      // 版本失败只改变恢复能力，不显示技术原因，也不阻塞网页版。
    }
  }

  Future<bool> openUpdate() async {
    if (_openingExternalTarget || !snapshot.showsUpdate) return false;
    _setOpeningExternalTarget(true);
    try {
      if (await _nativeBridge.openTrustedExternalUrl(snapshot.updateUrl)) {
        _updateTargetOpened = true;
        return true;
      }
      final opened = await _nativeBridge.openTrustedExternalUrl(
        snapshot.recoveryUrl,
      );
      _updateTargetOpened = opened;
      return opened;
    } finally {
      _setOpeningExternalTarget(false);
    }
  }

  void refreshVersionAfterExternalReturn() {
    if (!_updateTargetOpened) return;
    _updateTargetOpened = false;
    if (!_stateMachine.restartVersionCheckAfterUpdate()) return;
    notifyListeners();
    _startVersionCheck();
  }

  Future<bool> openWeb() async {
    if (_openingExternalTarget) return false;
    _setOpeningExternalTarget(true);
    try {
      final context = _nativeContext ?? await _nativeBridge.context();
      final webUrl = context?.publicWebUrl ?? '';
      if (await _nativeBridge.openTrustedExternalUrl(webUrl)) {
        return true;
      }
      final fallback = snapshot.recoveryUrl;
      return fallback.isNotEmpty &&
          await _nativeBridge.openTrustedExternalUrl(fallback);
    } finally {
      _setOpeningExternalTarget(false);
    }
  }

  void _setOpeningExternalTarget(bool value) {
    if (_openingExternalTarget == value) return;
    _openingExternalTarget = value;
    notifyListeners();
  }

  @override
  void dispose() {
    _visibleCheckTimer?.cancel();
    super.dispose();
  }
}
