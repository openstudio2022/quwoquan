import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

class CallTimerState {
  final Duration elapsed;
  final bool isRunning;

  const CallTimerState({
    this.elapsed = Duration.zero,
    this.isRunning = false,
  });

  String get formattedTime {
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

  CallTimerState copyWith({
    Duration? elapsed,
    bool? isRunning,
  }) {
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
  CallTimerState build() => const CallTimerState();

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

final callTimerProvider =
    NotifierProvider<CallTimerNotifier, CallTimerState>(
  CallTimerNotifier.new,
);
