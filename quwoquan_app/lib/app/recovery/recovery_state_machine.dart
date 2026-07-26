import 'package:flutter/foundation.dart';

enum RecoveryPhase {
  startupChecking,
  startupUpdateRequired,
  startupLatest,
  startupVersionUnavailable,
  runtimeUnavailable,
  runtimeReentering,
}

@immutable
class RecoverySnapshot {
  const RecoverySnapshot({
    required this.phase,
    this.updateUrl = '',
    this.recoveryUrl = '',
  });

  const RecoverySnapshot.startupChecking()
    : this(phase: RecoveryPhase.startupChecking);

  final RecoveryPhase phase;
  final String updateUrl;
  final String recoveryUrl;

  bool get showsUpdate => phase == RecoveryPhase.startupUpdateRequired;
  bool get showsWebSecondary =>
      phase == RecoveryPhase.startupChecking ||
      phase == RecoveryPhase.startupUpdateRequired ||
      phase == RecoveryPhase.runtimeUnavailable ||
      phase == RecoveryPhase.runtimeReentering;
}

final class RecoveryStateMachine {
  RecoveryStateMachine({RecoverySnapshot? initial})
    : _snapshot = initial ?? const RecoverySnapshot.startupChecking();

  RecoverySnapshot _snapshot;
  bool _terminalVersionConfirmed = false;
  bool _runtimeReentryAttempted = false;

  RecoverySnapshot get snapshot => _snapshot;

  bool confirmVersion({
    required int currentBuild,
    required int latestBuild,
    required String updateUrl,
    required String recoveryUrl,
  }) {
    if (_terminalVersionConfirmed ||
        currentBuild <= 0 ||
        latestBuild <= 0 ||
        !_isTrustedHttps(updateUrl) ||
        !_isTrustedHttps(recoveryUrl)) {
      return false;
    }
    _terminalVersionConfirmed = true;
    _snapshot = latestBuild > currentBuild
        ? RecoverySnapshot(
            phase: RecoveryPhase.startupUpdateRequired,
            updateUrl: updateUrl,
            recoveryUrl: recoveryUrl,
          )
        : RecoverySnapshot(
            phase: RecoveryPhase.startupLatest,
            recoveryUrl: recoveryUrl,
          );
    return true;
  }

  bool markVersionUnavailable() {
    if (_terminalVersionConfirmed ||
        _snapshot.phase != RecoveryPhase.startupChecking) {
      return false;
    }
    _snapshot = const RecoverySnapshot(
      phase: RecoveryPhase.startupVersionUnavailable,
    );
    return true;
  }

  bool beginRuntimeReentry() {
    if (_runtimeReentryAttempted ||
        _snapshot.phase != RecoveryPhase.runtimeUnavailable) {
      return false;
    }
    _runtimeReentryAttempted = true;
    _snapshot = const RecoverySnapshot(phase: RecoveryPhase.runtimeReentering);
    return true;
  }

  bool failRuntimeReentry() {
    if (_snapshot.phase != RecoveryPhase.runtimeReentering) {
      return false;
    }
    _snapshot = const RecoverySnapshot.startupChecking();
    return true;
  }

  static bool _isTrustedHttps(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null ||
        uri.scheme.toLowerCase() != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty) {
      return false;
    }
    final host = uri.host.toLowerCase();
    return host == 'apps.apple.com' ||
        host == 'quwoquan.com' ||
        host.endsWith('.quwoquan.com') ||
        host == 'quwoquan-env.test' ||
        host.endsWith('.quwoquan-env.test');
  }
}
