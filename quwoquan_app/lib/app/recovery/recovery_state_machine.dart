import 'package:flutter/foundation.dart';

enum RecoveryPhase {
  startupChecking,
  startupUpdateRequired,
  startupLatest,
  startupVersionUnavailable,
  runtimeUnavailable,
  runtimeReentering,
  runtimeVersionChecking,
  runtimeUpdateRequired,
  runtimeLatest,
  runtimeVersionUnavailable,
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

  bool get showsUpdate =>
      phase == RecoveryPhase.startupUpdateRequired ||
      phase == RecoveryPhase.runtimeUpdateRequired;
  bool get showsWebSecondary =>
      phase == RecoveryPhase.startupChecking ||
      phase == RecoveryPhase.startupUpdateRequired ||
      phase == RecoveryPhase.runtimeUnavailable ||
      phase == RecoveryPhase.runtimeReentering ||
      phase == RecoveryPhase.runtimeVersionChecking ||
      phase == RecoveryPhase.runtimeUpdateRequired;
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
    final runtimeContext =
        _snapshot.phase == RecoveryPhase.runtimeVersionChecking ||
        _snapshot.phase == RecoveryPhase.runtimeVersionUnavailable;
    _terminalVersionConfirmed = true;
    _snapshot = latestBuild > currentBuild
        ? RecoverySnapshot(
            phase: runtimeContext
                ? RecoveryPhase.runtimeUpdateRequired
                : RecoveryPhase.startupUpdateRequired,
            updateUrl: updateUrl,
            recoveryUrl: recoveryUrl,
          )
        : RecoverySnapshot(
            phase: runtimeContext
                ? RecoveryPhase.runtimeLatest
                : RecoveryPhase.startupLatest,
            recoveryUrl: recoveryUrl,
          );
    return true;
  }

  bool markVersionUnavailable() {
    if (_terminalVersionConfirmed) {
      return false;
    }
    final nextPhase = switch (_snapshot.phase) {
      RecoveryPhase.startupChecking => RecoveryPhase.startupVersionUnavailable,
      RecoveryPhase.runtimeVersionChecking =>
        RecoveryPhase.runtimeVersionUnavailable,
      _ => null,
    };
    if (nextPhase == null) return false;
    _snapshot = RecoverySnapshot(phase: nextPhase);
    return true;
  }

  bool restartVersionCheckAfterUpdate() {
    _terminalVersionConfirmed = false;
    switch (_snapshot.phase) {
      case RecoveryPhase.startupUpdateRequired:
        _snapshot = const RecoverySnapshot.startupChecking();
        return true;
      case RecoveryPhase.runtimeUpdateRequired:
        _snapshot = const RecoverySnapshot(
          phase: RecoveryPhase.runtimeVersionChecking,
        );
        return true;
      default:
        _terminalVersionConfirmed =
            _snapshot.phase == RecoveryPhase.startupLatest ||
            _snapshot.phase == RecoveryPhase.runtimeLatest;
        return false;
    }
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
    _snapshot = const RecoverySnapshot(
      phase: RecoveryPhase.runtimeVersionChecking,
    );
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
