import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 通话时长展示格式的单一真相源：>1h 显示 HH:MM:SS，否则 MM:SS。
///
/// 通话页、ActiveCallBar、PiP 浮窗必须消费本函数；禁止在 presentation
/// 内自写 `_formatDuration`（历史缺陷：丢弃小时位导致长通话显示错误）。
String formatCallDuration(Duration elapsed) {
  final hours = elapsed.inHours;
  final minutes = elapsed.inMinutes.remainder(60);
  final seconds = elapsed.inSeconds.remainder(60);

  if (hours > 0) {
    return '${hours.toString().padLeft(2, '0')}:'
        '${minutes.toString().padLeft(2, '0')}:'
        '${seconds.toString().padLeft(2, '0')}';
  }
  return '${minutes.toString().padLeft(2, '0')}:'
      '${seconds.toString().padLeft(2, '0')}';
}

class CallTimerState {
  final Duration elapsed;
  final bool isRunning;

  const CallTimerState({this.elapsed = Duration.zero, this.isRunning = false});

  String get formattedTime => formatCallDuration(elapsed);

  CallTimerState copyWith({Duration? elapsed, bool? isRunning}) {
    return CallTimerState(
      elapsed: elapsed ?? this.elapsed,
      isRunning: isRunning ?? this.isRunning,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallTimerState &&
          runtimeType == other.runtimeType &&
          elapsed == other.elapsed &&
          isRunning == other.isRunning;

  @override
  int get hashCode => Object.hash(elapsed, isRunning);
}

class CallTimerNotifier extends Notifier<CallTimerState> {
  Timer? _timer;

  @override
  CallTimerState build() {
    // notifier 回收时必须取消周期计时器，否则残留回调会在容器销毁后
    // 触碰已释放的 Ref（登出/重启等容器生命周期路径）。
    ref.onDispose(() {
      _timer?.cancel();
      _timer = null;
    });
    return const CallTimerState();
  }

  void start() {
    if (state.isRunning) return;
    state = state.copyWith(isRunning: true, elapsed: Duration.zero);
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      state = state.copyWith(
        elapsed: state.elapsed + const Duration(seconds: 1),
      );
    });
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    state = state.copyWith(isRunning: false);
  }

  void reset() {
    _timer?.cancel();
    _timer = null;
    state = const CallTimerState();
  }
}

final callTimerProvider = NotifierProvider<CallTimerNotifier, CallTimerState>(
  CallTimerNotifier.new,
);
