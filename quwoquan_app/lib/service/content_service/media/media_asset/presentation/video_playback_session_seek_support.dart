part of 'video_playback_session.dart';

enum _VideoSeekPurpose { userRelease, sourceSwitch }

enum _VideoSeekWaitDisposition {
  completed,
  failed,
  deadlineExceeded,
  capacityExceeded,
  terminal,
}

final class _VideoSeekCommandAdmission {
  static const int maxUnresolvedPerSession = 2;
  static const int maxUnresolvedPerController = 2;

  final Map<VideoPlayerController, int> _unresolvedByController =
      Map<VideoPlayerController, int>.identity();
  int _totalUnresolved = 0;

  int get unresolvedControllerCount => _unresolvedByController.length;
  int get totalUnresolved => _totalUnresolved;

  bool tryAcquire(VideoPlayerController controller) {
    final unresolved = _unresolvedByController[controller] ?? 0;
    if (_totalUnresolved >= maxUnresolvedPerSession ||
        unresolved >= maxUnresolvedPerController) {
      return false;
    }
    _unresolvedByController[controller] = unresolved + 1;
    _totalUnresolved += 1;
    return true;
  }

  void release(VideoPlayerController controller) {
    final unresolved = _unresolvedByController[controller];
    if (unresolved == null) {
      return;
    }
    if (_totalUnresolved > 0) {
      _totalUnresolved -= 1;
    }
    if (unresolved <= 1) {
      _unresolvedByController.remove(controller);
      return;
    }
    _unresolvedByController[controller] = unresolved - 1;
  }
}

final class _VideoSeekDeadline {
  _VideoSeekDeadline(Duration requested)
    : timeout = requested > Duration.zero
          ? requested
          : const Duration(milliseconds: 1),
      stopwatch = Stopwatch()..start();

  final Duration timeout;
  final Stopwatch stopwatch;

  Duration get remaining {
    final value = timeout - stopwatch.elapsed;
    return value > Duration.zero ? value : Duration.zero;
  }

  int get elapsedMs => stopwatch.elapsedMilliseconds;
}

final class _VideoSeekWaitResult {
  const _VideoSeekWaitResult._(
    this.disposition, {
    this.value,
    this.error,
    this.stackTrace,
  });

  const _VideoSeekWaitResult.completed(Object? value)
    : this._(_VideoSeekWaitDisposition.completed, value: value);

  const _VideoSeekWaitResult.failed(Object error, StackTrace stackTrace)
    : this._(
        _VideoSeekWaitDisposition.failed,
        error: error,
        stackTrace: stackTrace,
      );

  const _VideoSeekWaitResult.deadlineExceeded()
    : this._(_VideoSeekWaitDisposition.deadlineExceeded);

  const _VideoSeekWaitResult.capacityExceeded()
    : this._(_VideoSeekWaitDisposition.capacityExceeded);

  const _VideoSeekWaitResult.terminal()
    : this._(_VideoSeekWaitDisposition.terminal);

  final _VideoSeekWaitDisposition disposition;
  final Object? value;
  final Object? error;
  final StackTrace? stackTrace;
}
