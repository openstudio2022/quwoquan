import 'dart:async';

import 'package:flutter/foundation.dart';

typedef DraftSessionFlushCallback = Future<void> Function(String reason);
typedef DraftSessionFlushFailureCallback =
    void Function(Object error, StackTrace stackTrace, String reason);

enum CreateDraftSaveStatus { idle, dirty, saving, saved, failed }

/// 管理创作页草稿会话的 dirty/定时保存/丢弃抑制语义。
class CreateDraftSessionController {
  CreateDraftSessionController({
    required this._onFlushDirty,
    this.onFlushFailure,
    this._interval = const Duration(seconds: 10),
  });

  final DraftSessionFlushCallback _onFlushDirty;
  final DraftSessionFlushFailureCallback? onFlushFailure;
  final Duration _interval;

  Timer? _timer;
  bool _dirty = false;
  bool _suppressed = false;
  bool _isFlushing = false;
  bool _flushQueued = false;
  int _dirtyVersion = 0;
  final ValueNotifier<CreateDraftSaveStatus> saveStatusListenable =
      ValueNotifier<CreateDraftSaveStatus>(CreateDraftSaveStatus.idle);

  bool get isDirty => _dirty;
  bool get isSuppressed => _suppressed;
  CreateDraftSaveStatus get saveStatus => saveStatusListenable.value;

  void start() {
    _timer ??= Timer.periodic(_interval, (_) {
      unawaited(flushIfDirty(reason: 'timer'));
    });
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
    saveStatusListenable.dispose();
  }

  void markDirty() {
    _suppressed = false;
    _dirty = true;
    _dirtyVersion += 1;
    _setSaveStatus(CreateDraftSaveStatus.dirty);
  }

  void markClean() {
    _dirty = false;
    _setSaveStatus(CreateDraftSaveStatus.saved);
  }

  void markSaving() {
    _setSaveStatus(CreateDraftSaveStatus.saving);
  }

  void markSaved() {
    _dirty = false;
    _setSaveStatus(CreateDraftSaveStatus.saved);
  }

  void markFailed() {
    _dirty = true;
    _setSaveStatus(CreateDraftSaveStatus.failed);
  }

  void markIdle() {
    _dirty = false;
    _setSaveStatus(CreateDraftSaveStatus.idle);
  }

  void suppressAfterDiscard() {
    _suppressed = true;
    _dirty = false;
    _dirtyVersion += 1;
    _setSaveStatus(CreateDraftSaveStatus.idle);
  }

  void resumeAfterRestore() {
    _suppressed = false;
    _dirty = false;
    _setSaveStatus(CreateDraftSaveStatus.idle);
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
    markSaving();
    try {
      await _onFlushDirty(reason);
      if (!_suppressed && snapshotVersion == _dirtyVersion) {
        markSaved();
      }
    } catch (error, stackTrace) {
      markFailed();
      onFlushFailure?.call(error, stackTrace, reason);
    } finally {
      _isFlushing = false;
    }
    if (_flushQueued) {
      _flushQueued = false;
      await flushIfDirty(reason: 'queued');
    }
  }

  void _setSaveStatus(CreateDraftSaveStatus status) {
    if (saveStatusListenable.value == status) {
      return;
    }
    saveStatusListenable.value = status;
  }
}
