import 'dart:async';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// App 内异步等待只保留三种交互模式。
enum AppRequestWaitMode { foreground, action, longTask }

/// 全 App 共用的三个等待语义时间点。
abstract final class AppRequestWaitTimings {
  static const Duration localLookupDeadline = Duration(milliseconds: 1500);
  static const Duration blockedSlowHint = Duration(seconds: 3);
  static const Duration foregroundReadDeadline = Duration(seconds: 6);
}

typedef AppRequestWaitObserver =
    void Function(String phase, int durationMilliseconds);

/// 只管理等待生命周期，不替代页面现有的 AsyncValue、领域 state 或 RuntimeFailure。
///
/// 每次 [start] 都会 supersede 上一次 generation，并通过真实 cancellation signal
/// 终止仍在传输或退避中的旧 operation。调用方只允许使用当前 generation 回写业务状态。
final class AppRequestWaitController {
  AppRequestWaitController({
    DateTime Function()? now,
    Timer Function(Duration, void Function())? createTimer,
  }) : _now = now ?? DateTime.now,
       _createTimer = createTimer ?? _defaultCreateTimer;

  final DateTime Function() _now;
  final Timer Function(Duration, void Function()) _createTimer;

  Timer? _slowTimer;
  Timer? _deadlineTimer;
  CloudOperationCancellationSignal? _cancellation;
  DateTime? _startedAt;
  AppRequestWaitObserver? _observer;
  void Function(int generation)? _onSlow;
  void Function(int generation)? _onTimeout;
  int _generation = 0;
  bool _isPending = false;
  bool _isSlow = false;
  bool _isDisposed = false;

  int get generation => _generation;
  bool get isPending => _isPending;
  bool get isSlow => _isSlow;
  bool get isDisposed => _isDisposed;

  /// 开始一个新的等待范围。
  ///
  /// - foreground 默认使用 6 秒 deadline；本地查找应显式传 1.5 秒。
  /// - action 必须传 operation metadata 的 deadline。
  /// - longTask 默认无 deadline，不会被 6 秒误杀。
  int start({
    required AppRequestWaitMode mode,
    Duration? deadline,
    bool showSlowHint = true,
    CloudOperationCancellationSignal? cancellation,
    void Function(int generation)? onSlow,
    void Function(int generation)? onTimeout,
    AppRequestWaitObserver? observer,
  }) {
    _ensureUsable();
    _terminateCurrent(phase: 'cancelled', notifyObserver: _isPending);
    final nextGeneration = ++_generation;
    final effectiveDeadline = switch (mode) {
      AppRequestWaitMode.foreground =>
        deadline ?? AppRequestWaitTimings.foregroundReadDeadline,
      AppRequestWaitMode.action =>
        deadline ?? (throw ArgumentError.notNull('deadline')),
      AppRequestWaitMode.longTask => deadline,
    };

    _isPending = true;
    _isSlow = false;
    _startedAt = _now();
    _observer = observer;
    _onSlow = onSlow;
    _onTimeout = onTimeout;
    _cancellation = cancellation;

    if (showSlowHint &&
        mode != AppRequestWaitMode.longTask &&
        (effectiveDeadline == null ||
            effectiveDeadline > AppRequestWaitTimings.blockedSlowHint)) {
      _slowTimer = _createTimer(AppRequestWaitTimings.blockedSlowHint, () {
        if (!isCurrent(nextGeneration)) return;
        _isSlow = true;
        _record('slow');
        _onSlow?.call(nextGeneration);
      });
    }
    if (effectiveDeadline != null) {
      _deadlineTimer = _createTimer(effectiveDeadline, () {
        if (!isCurrent(nextGeneration)) return;
        _slowTimer?.cancel();
        _slowTimer = null;
        _deadlineTimer = null;
        _isPending = false;
        _isSlow = false;
        _cancellation?.cancel();
        _record('timeout');
        _onTimeout?.call(nextGeneration);
        _clearCallbacks();
      });
    }
    return nextGeneration;
  }

  bool isCurrent(int generation) {
    return !_isDisposed && _isPending && generation == _generation;
  }

  /// 正常终止当前 generation。旧 generation 的 completion 会被忽略。
  bool complete(int generation) {
    if (!isCurrent(generation)) return false;
    _cancelTimers();
    _isPending = false;
    _isSlow = false;
    _record('complete');
    _clearCallbacks();
    return true;
  }

  /// 查询变化、返回或业务主动取消时终止当前 generation。
  void cancel() {
    if (_isDisposed) return;
    _terminateCurrent(phase: 'cancelled', notifyObserver: _isPending);
    _generation += 1;
  }

  void dispose() {
    if (_isDisposed) return;
    _terminateCurrent(phase: 'cancelled', notifyObserver: false);
    _generation += 1;
    _isDisposed = true;
  }

  void _terminateCurrent({
    required String phase,
    required bool notifyObserver,
  }) {
    _cancelTimers();
    if (_isPending) {
      _cancellation?.cancel();
      if (notifyObserver) _record(phase);
    }
    _isPending = false;
    _isSlow = false;
    _clearCallbacks();
  }

  void _cancelTimers() {
    _slowTimer?.cancel();
    _deadlineTimer?.cancel();
    _slowTimer = null;
    _deadlineTimer = null;
  }

  void _clearCallbacks() {
    _cancellation = null;
    _observer = null;
    _onSlow = null;
    _onTimeout = null;
    _startedAt = null;
  }

  void _record(String phase) {
    final startedAt = _startedAt;
    final duration = startedAt == null
        ? 0
        : _now().difference(startedAt).inMilliseconds;
    _observer?.call(phase, duration < 0 ? 0 : duration);
  }

  void _ensureUsable() {
    if (_isDisposed) {
      throw StateError('AppRequestWaitController has been disposed');
    }
  }
}

Timer _defaultCreateTimer(Duration duration, void Function() callback) {
  return Timer(duration, callback);
}
