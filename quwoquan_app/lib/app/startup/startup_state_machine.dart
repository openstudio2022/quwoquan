import 'package:flutter/foundation.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 根启动路径的唯一状态真相源。
///
/// Welcome、Router 与 Shell 的异步竞争不能直接翻转散落的布尔值；每个外部回调只能把
/// 状态推进到一个可见终态，过期的 Router 尝试也不能覆盖较新的恢复状态。
enum StartupRootPhase { welcome, routerLoading, routerShell, safeRecovery }

@immutable
class StartupRootSnapshot {
  const StartupRootSnapshot._({
    required this.phase,
    required this.welcomeOverlayVisible,
    required this.welcomeOverlayOpacity,
    this.failure,
  });

  const StartupRootSnapshot.welcome()
    : this._(
        phase: StartupRootPhase.welcome,
        welcomeOverlayVisible: false,
        welcomeOverlayOpacity: 1,
      );

  final StartupRootPhase phase;
  final bool welcomeOverlayVisible;
  final double welcomeOverlayOpacity;
  final RuntimeFailureBase? failure;

  StartupRootSnapshot copyWith({
    StartupRootPhase? phase,
    bool? welcomeOverlayVisible,
    double? welcomeOverlayOpacity,
    RuntimeFailureBase? failure,
    bool clearFailure = false,
  }) {
    return StartupRootSnapshot._(
      phase: phase ?? this.phase,
      welcomeOverlayVisible:
          welcomeOverlayVisible ?? this.welcomeOverlayVisible,
      welcomeOverlayOpacity:
          welcomeOverlayOpacity ?? this.welcomeOverlayOpacity,
      failure: clearFailure ? null : (failure ?? this.failure),
    );
  }
}

final class StartupStateMachine {
  StartupRootSnapshot _snapshot = const StartupRootSnapshot.welcome();
  bool _welcomeCompletionRequested = false;
  int _routerAttempt = 0;

  StartupRootSnapshot get snapshot => _snapshot;
  bool get welcomeCompletionRequested => _welcomeCompletionRequested;
  int get currentRouterAttempt => _routerAttempt;

  /// `onFinish`、root deadline 和 lifecycle 只允许一个调用者取得完成权。
  bool requestWelcomeCompletion() {
    if (_welcomeCompletionRequested ||
        _snapshot.phase == StartupRootPhase.routerShell ||
        _snapshot.phase == StartupRootPhase.safeRecovery) {
      return false;
    }
    _welcomeCompletionRequested = true;
    return true;
  }

  int beginRouterLoad({bool showWelcomeOverlay = true}) {
    if (_snapshot.phase == StartupRootPhase.routerShell) {
      return _routerAttempt;
    }
    _routerAttempt += 1;
    _snapshot = _snapshot.copyWith(
      phase: StartupRootPhase.routerLoading,
      welcomeOverlayVisible: showWelcomeOverlay,
      welcomeOverlayOpacity: 1,
      clearFailure: true,
    );
    return _routerAttempt;
  }

  bool markRouterReady(int attempt) {
    if (attempt != _routerAttempt ||
        _snapshot.phase != StartupRootPhase.routerLoading) {
      return false;
    }
    _snapshot = _snapshot.copyWith(
      phase: StartupRootPhase.routerShell,
      welcomeOverlayVisible: _snapshot.welcomeOverlayVisible,
      welcomeOverlayOpacity: 1,
      clearFailure: true,
    );
    return true;
  }

  bool markRouterFailure(int attempt, RuntimeFailureBase failure) {
    if (attempt != _routerAttempt ||
        _snapshot.phase != StartupRootPhase.routerLoading) {
      return false;
    }
    _snapshot = _snapshot.copyWith(
      phase: StartupRootPhase.safeRecovery,
      welcomeOverlayVisible: false,
      welcomeOverlayOpacity: 0,
      failure: failure,
    );
    return true;
  }

  void forceSafeRecovery(RuntimeFailureBase failure) {
    if (_snapshot.phase == StartupRootPhase.routerShell) {
      return;
    }
    _routerAttempt += 1;
    _snapshot = _snapshot.copyWith(
      phase: StartupRootPhase.safeRecovery,
      welcomeOverlayVisible: false,
      welcomeOverlayOpacity: 0,
      failure: failure,
    );
  }

  bool beginOverlayFade() {
    if (_snapshot.phase != StartupRootPhase.routerShell ||
        !_snapshot.welcomeOverlayVisible) {
      return false;
    }
    _snapshot = _snapshot.copyWith(welcomeOverlayOpacity: 0);
    return true;
  }

  bool removeWelcomeOverlay() {
    if (!_snapshot.welcomeOverlayVisible) {
      return false;
    }
    _snapshot = _snapshot.copyWith(
      welcomeOverlayVisible: false,
      welcomeOverlayOpacity: 0,
    );
    return true;
  }
}
