import 'dart:async';

typedef DraftSessionFlushCallback = Future<void> Function(String reason);

/// 管理创作页草稿会话的 dirty/定时保存/丢弃抑制语义。
class CreateDraftSessionController {
  CreateDraftSessionController({
    required this._onFlushDirty,
    this._interval = const Duration(seconds: 10),
  });

  final DraftSessionFlushCallback _onFlushDirty;
  final Duration _interval;

  Timer? _timer;
  bool _dirty = false;
  bool _suppressed = false;
  bool _isFlushing = false;
  bool _flushQueued = false;
  int _dirtyVersion = 0;

  bool get isDirty => _dirty;
  bool get isSuppressed => _suppressed;

  void start() {
    _timer ??= Timer.periodic(_interval, (_) {
      unawaited(flushIfDirty(reason: 'timer'));
    });
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }

  void markDirty() {
    _suppressed = false;
    _dirty = true;
    _dirtyVersion += 1;
  }

  void markClean() {
    _dirty = false;
  }

  void suppressAfterDiscard() {
    _suppressed = true;
    _dirty = false;
    _dirtyVersion += 1;
  }

  void resumeAfterRestore() {
    _suppressed = false;
    _dirty = false;
  }

  Future<void> flushIfDirty({String reason = 'manual'}) async {
    if (_suppressed || !_dirty) {
      return;
    }
    if (_isFlushing) {
      _flushQueued = true;
      return;
    }
    final snapshotVersion = _dirtyVersion;
    _isFlushing = true;
    try {
      await _onFlushDirty(reason);
      if (!_suppressed && snapshotVersion == _dirtyVersion) {
        _dirty = false;
      }
    } finally {
      _isFlushing = false;
    }
    if (_flushQueued) {
      _flushQueued = false;
      await flushIfDirty(reason: 'queued');
    }
  }
}
