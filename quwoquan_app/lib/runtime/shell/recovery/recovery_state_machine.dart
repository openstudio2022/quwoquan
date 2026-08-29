import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/transport/links/trusted_endpoint_policy.dart';

enum RecoveryPhase {
  startupChecking,
  startupUpdateRequired,
  startupWebOnly,
  startupLatest,
  startupVersionUnavailable,
  runtimeUnavailable,
  runtimeReentering,
  runtimeVersionChecking,
  runtimeUpdateRequired,
  runtimeWebOnly,
  runtimeLatest,
  runtimeVersionUnavailable,
}

enum RecoveryWebTargetSource { none, confirmedRecoveryUrl, nativePublicWebUrl }

@immutable
class RecoverySnapshot {
  const RecoverySnapshot({
    required this.phase,
    this.updateState = RecoveryUpdateState.none,
    this.updateUrl = '',
    this.recoveryUrl = '',
  });

  const RecoverySnapshot.startupChecking()
    : this(phase: RecoveryPhase.startupChecking);

  final RecoveryPhase phase;
  final RecoveryUpdateState updateState;
  final String updateUrl;
  final String recoveryUrl;

  bool get showsUpdate =>
      phase == RecoveryPhase.startupUpdateRequired ||
      phase == RecoveryPhase.runtimeUpdateRequired;
  bool get requiresUpdate => updateState == RecoveryUpdateState.required;
  bool get isWebOnly =>
      phase == RecoveryPhase.startupWebOnly ||
      phase == RecoveryPhase.runtimeWebOnly;
  bool get isVersionUnavailable =>
      phase == RecoveryPhase.startupVersionUnavailable ||
      phase == RecoveryPhase.runtimeVersionUnavailable;
  bool get showsWebSecondary =>
      phase == RecoveryPhase.startupChecking ||
      phase == RecoveryPhase.startupUpdateRequired ||
      phase == RecoveryPhase.runtimeUnavailable ||
      phase == RecoveryPhase.runtimeReentering ||
      phase == RecoveryPhase.runtimeVersionChecking ||
      phase == RecoveryPhase.runtimeUpdateRequired;

  RecoveryWebTargetSource get webTargetSource {
    if (recoveryUrl.trim().isNotEmpty) {
      return RecoveryWebTargetSource.confirmedRecoveryUrl;
    }
    return switch (phase) {
      RecoveryPhase.startupChecking ||
      RecoveryPhase.startupVersionUnavailable ||
      RecoveryPhase.runtimeUnavailable ||
      RecoveryPhase.runtimeReentering ||
      RecoveryPhase.runtimeVersionChecking ||
      RecoveryPhase.runtimeVersionUnavailable =>
        RecoveryWebTargetSource.nativePublicWebUrl,
      _ => RecoveryWebTargetSource.none,
    };
  }
}

final class RecoveryStateMachine {
  RecoveryStateMachine({RecoverySnapshot? initial})
    : _snapshot = initial ?? const RecoverySnapshot.startupChecking(),
      _terminalVersionConfirmed = _isConfirmedVersionPhase(
        (initial ?? const RecoverySnapshot.startupChecking()).phase,
      );

  RecoverySnapshot _snapshot;
  bool _terminalVersionConfirmed;
  bool _runtimeReentryAttempted = false;

  RecoverySnapshot get snapshot => _snapshot;

  static bool _isConfirmedVersionPhase(RecoveryPhase phase) =>
      phase == RecoveryPhase.startupUpdateRequired ||
      phase == RecoveryPhase.startupWebOnly ||
      phase == RecoveryPhase.startupLatest ||
      phase == RecoveryPhase.runtimeUpdateRequired ||
      phase == RecoveryPhase.runtimeWebOnly ||
      phase == RecoveryPhase.runtimeLatest;

  bool confirmVersion({
    required RecoveryVersionPlatform platform,
    required int currentBuild,
    required int latestBuild,
    required int minimumSupportedBuild,
    required RecoveryUpdateState updateState,
    required RecoveryVersionChannel updateChannel,
    bool requiredUpdateOnly = false,
    required String? updateUrl,
    required String recoveryUrl,
    required Iterable<String> trustedBaseUrls,
  }) {
    final expectedUpdateState = switch (currentBuild) {
      final build when build < minimumSupportedBuild =>
        RecoveryUpdateState.required,
      final build when build < latestBuild => RecoveryUpdateState.available,
      _ => RecoveryUpdateState.none,
    };
    final hasUpdate = updateState != RecoveryUpdateState.none;
    final normalizedUpdateUrl = updateUrl?.trim();
    final normalizedRecoveryUrl = recoveryUrl.trim();
    final canonicalUpdateChannel = hasCanonicalRecoveryVersionTarget(
      platform: platform,
      channel: updateChannel,
      updateUrl: normalizedUpdateUrl,
    );
    final trustedUpdateTarget =
        updateChannel != RecoveryVersionChannel.nativeUpdate ||
        (normalizedUpdateUrl != null &&
            isTrustedHttpsUrl(normalizedUpdateUrl, trustedBaseUrls));
    if (_terminalVersionConfirmed ||
        currentBuild <= 0 ||
        latestBuild <= 0 ||
        minimumSupportedBuild <= 0 ||
        minimumSupportedBuild > latestBuild ||
        updateState != expectedUpdateState ||
        (requiredUpdateOnly && updateState != RecoveryUpdateState.required) ||
        !canonicalUpdateChannel ||
        !trustedUpdateTarget ||
        !isTrustedHttpsUrl(normalizedRecoveryUrl, trustedBaseUrls)) {
      return false;
    }
    final runtimeContext =
        _snapshot.phase == RecoveryPhase.runtimeVersionChecking ||
        _snapshot.phase == RecoveryPhase.runtimeVersionUnavailable;
    _terminalVersionConfirmed = true;
    if (hasUpdate && updateChannel == RecoveryVersionChannel.webOnly) {
      _snapshot = RecoverySnapshot(
        phase: runtimeContext
            ? RecoveryPhase.runtimeWebOnly
            : RecoveryPhase.startupWebOnly,
        updateState: updateState,
        recoveryUrl: normalizedRecoveryUrl,
      );
      return true;
    }
    _snapshot = hasUpdate
        ? RecoverySnapshot(
            phase: runtimeContext
                ? RecoveryPhase.runtimeUpdateRequired
                : RecoveryPhase.startupUpdateRequired,
            updateState: updateState,
            updateUrl: normalizedUpdateUrl!,
            recoveryUrl: normalizedRecoveryUrl,
          )
        : RecoverySnapshot(
            phase: runtimeContext
                ? RecoveryPhase.runtimeLatest
                : RecoveryPhase.startupLatest,
            recoveryUrl: normalizedRecoveryUrl,
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
        _terminalVersionConfirmed = _isConfirmedVersionPhase(_snapshot.phase);
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
}
