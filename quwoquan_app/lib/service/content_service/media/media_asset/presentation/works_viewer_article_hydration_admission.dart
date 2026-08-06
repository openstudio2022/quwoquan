import 'dart:async';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum WorksViewerArticleHydrationOutcome { completed, superseded, disposed }

final class WorksViewerArticleHydrationLease {
  const WorksViewerArticleHydrationLease({
    required this.postId,
    required this.cancellation,
  });

  final String postId;
  final CloudOperationCancellationSignal cancellation;

  bool get isCancelled => cancellation.isCancelled;
}

typedef WorksViewerArticleHydrationTask =
    Future<void> Function(WorksViewerArticleHydrationLease lease);

/// Serial, latest-only admission for Work Browser article detail hydration.
///
/// At most one task is executing. A newer post cooperatively cancels the active
/// request and replaces the single pending request; it never builds an
/// unbounded Future chain while the user swipes quickly.
final class WorksViewerArticleHydrationAdmission {
  _QueuedArticleHydration? _active;
  _QueuedArticleHydration? _pending;
  bool _draining = false;
  bool _disposed = false;

  int get activeCount => _active == null ? 0 : 1;
  int get pendingCount => _pending == null ? 0 : 1;

  bool contains(String postId) {
    final normalized = postId.trim();
    return normalized.isNotEmpty &&
        ((_active?.lease.postId == normalized &&
                _active?.lease.isCancelled == false) ||
            _pending?.lease.postId == normalized);
  }

  Future<WorksViewerArticleHydrationOutcome> schedule({
    required String postId,
    required WorksViewerArticleHydrationTask task,
  }) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(postId, 'postId', 'must not be empty');
    }
    if (_disposed) {
      return Future<WorksViewerArticleHydrationOutcome>.value(
        WorksViewerArticleHydrationOutcome.disposed,
      );
    }

    final active = _active;
    if (active != null &&
        active.lease.postId == normalized &&
        !active.lease.isCancelled) {
      return active.completer.future;
    }
    final pending = _pending;
    if (pending != null && pending.lease.postId == normalized) {
      return pending.completer.future;
    }

    active?.lease.cancellation.cancel();
    _completePending(WorksViewerArticleHydrationOutcome.superseded);
    final queued = _QueuedArticleHydration(
      lease: WorksViewerArticleHydrationLease(
        postId: normalized,
        cancellation: CloudOperationCancellationSignal(),
      ),
      task: task,
    );
    _pending = queued;
    _ensureDrain();
    return queued.completer.future;
  }

  /// Cancels work that no longer belongs to the visible post. Passing null
  /// cancels all hydration, including when the viewport moves to non-article
  /// content or a load-more sentinel.
  void retainOnly(String? postId) {
    final normalized = postId?.trim();
    final retained = normalized == null || normalized.isEmpty
        ? null
        : normalized;
    final active = _active;
    if (active != null && active.lease.postId != retained) {
      active.lease.cancellation.cancel();
    }
    if (_pending?.lease.postId != retained) {
      _completePending(WorksViewerArticleHydrationOutcome.superseded);
    }
  }

  void cancelPost(String postId) {
    final normalized = postId.trim();
    if (_active?.lease.postId == normalized) {
      _active?.lease.cancellation.cancel();
    }
    if (_pending?.lease.postId == normalized) {
      _completePending(WorksViewerArticleHydrationOutcome.superseded);
    }
  }

  void dispose() {
    if (_disposed) {
      return;
    }
    _disposed = true;
    _active?.lease.cancellation.cancel();
    _completePending(WorksViewerArticleHydrationOutcome.disposed);
  }

  void _ensureDrain() {
    if (_draining) {
      return;
    }
    unawaited(_drain());
  }

  Future<void> _drain() async {
    if (_draining) {
      return;
    }
    _draining = true;
    try {
      while (!_disposed && _pending != null) {
        final queued = _pending!;
        _pending = null;
        _active = queued;
        var outcome = WorksViewerArticleHydrationOutcome.completed;
        try {
          if (queued.lease.isCancelled) {
            outcome = WorksViewerArticleHydrationOutcome.superseded;
          } else {
            await queued.task(queued.lease);
            if (queued.lease.isCancelled) {
              outcome = WorksViewerArticleHydrationOutcome.superseded;
            }
          }
        } catch (error, stackTrace) {
          if (queued.lease.isCancelled) {
            outcome = WorksViewerArticleHydrationOutcome.superseded;
          } else if (!queued.completer.isCompleted) {
            queued.completer.completeError(error, stackTrace);
          }
        } finally {
          if (identical(_active, queued)) {
            _active = null;
          }
          if (!queued.completer.isCompleted) {
            queued.completer.complete(outcome);
          }
        }
      }
    } finally {
      _draining = false;
      if (!_disposed && _pending != null) {
        _ensureDrain();
      }
    }
  }

  void _completePending(WorksViewerArticleHydrationOutcome outcome) {
    final pending = _pending;
    _pending = null;
    if (pending != null && !pending.completer.isCompleted) {
      pending.lease.cancellation.cancel();
      pending.completer.complete(outcome);
    }
  }
}

final class _QueuedArticleHydration {
  _QueuedArticleHydration({required this.lease, required this.task});

  final WorksViewerArticleHydrationLease lease;
  final WorksViewerArticleHydrationTask task;
  final Completer<WorksViewerArticleHydrationOutcome> completer =
      Completer<WorksViewerArticleHydrationOutcome>();
}
