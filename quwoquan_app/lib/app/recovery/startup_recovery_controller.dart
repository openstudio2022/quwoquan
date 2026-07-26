import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/app/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/app/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';

final class StartupRecoveryController extends ChangeNotifier {
  StartupRecoveryController({
    RecoveryVersionClient? versionClient,
    AppRecoveryNativeBridge? nativeBridge,
    this._visibleCheckBudget = const Duration(milliseconds: 1500),
    String recoveryBaseUrl = CloudRuntimeConfig.gatewayBaseUrl,
  }) : _versionClient = versionClient ?? RecoveryVersionClient(),
       _nativeBridge = nativeBridge ?? AppRecoveryNativeBridge(),
       _recoveryBaseUrl = recoveryBaseUrl;

  final RecoveryVersionClient _versionClient;
  final AppRecoveryNativeBridge _nativeBridge;
  final Duration _visibleCheckBudget;
  final String _recoveryBaseUrl;
  final RecoveryStateMachine _stateMachine = RecoveryStateMachine();

  Timer? _visibleCheckTimer;
  bool _started = false;
  bool _openingExternalTarget = false;

  RecoverySnapshot get snapshot => _stateMachine.snapshot;
  bool get openingExternalTarget => _openingExternalTarget;

  void start() {
    if (_started) return;
    _started = true;
    _visibleCheckTimer = Timer(_visibleCheckBudget, () {
      if (_stateMachine.markVersionUnavailable()) {
        notifyListeners();
      }
    });
    unawaited(_checkVersion());
  }

  Future<void> _checkVersion() async {
    try {
      final nativeContext = await _nativeBridge.context();
      if (nativeContext == null) return;
      final result = await _versionClient.fetch(
        baseUrl: _recoveryBaseUrl,
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
        return true;
      }
      return _nativeBridge.openTrustedExternalUrl(snapshot.recoveryUrl);
    } finally {
      _setOpeningExternalTarget(false);
    }
  }

  Future<bool> openWeb() async {
    if (_openingExternalTarget) return false;
    _setOpeningExternalTarget(true);
    try {
      final webUrl = AppPublicContentLinks.publicWebBaseUrl;
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
