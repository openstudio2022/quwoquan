import 'dart:async';

final class CloudOperationCancelledException implements Exception {
  const CloudOperationCancelledException();

  @override
  String toString() => 'Cloud operation cancelled';
}

/// Cooperative cancellation signal shared by executor, backoff and transport.
final class CloudOperationCancellationSignal {
  final Completer<void> _cancelled = Completer<void>();

  bool get isCancelled => _cancelled.isCompleted;
  Future<void> get whenCancelled => _cancelled.future;

  void cancel() {
    if (!_cancelled.isCompleted) {
      _cancelled.complete();
    }
  }

  void throwIfCancelled() {
    if (isCancelled) {
      throw const CloudOperationCancelledException();
    }
  }
}

/// Fails before starting a prerequisite when its request has already been
/// cancelled or its caller-owned deadline has expired.
void throwIfCloudOperationInterrupted({
  CloudOperationCancellationSignal? cancellation,
  DateTime? deadlineAt,
  DateTime Function()? now,
}) {
  cancellation?.throwIfCancelled();
  final effectiveNow = (now ?? DateTime.now)();
  if (deadlineAt != null && !deadlineAt.isAfter(effectiveNow)) {
    throw TimeoutException('Cloud operation prerequisite deadline exhausted');
  }
}

/// Runs local asynchronous prerequisite work under the same cancellation and
/// absolute deadline as the generated network operation. A blocked settings or
/// persistence loader must not keep a superseded request alive or allow it to
/// reach transport later.
Future<T> runCloudOperationPrerequisite<T>(
  Future<T> Function() start, {
  CloudOperationCancellationSignal? cancellation,
  DateTime? deadlineAt,
  DateTime Function()? now,
}) async {
  final clock = now ?? DateTime.now;
  throwIfCloudOperationInterrupted(
    cancellation: cancellation,
    deadlineAt: deadlineAt,
    now: clock,
  );

  final result = Completer<T>();
  Timer? deadlineTimer;
  final prerequisite = start();
  prerequisite.then(
    (value) {
      if (!result.isCompleted) {
        result.complete(value);
      }
    },
    onError: (Object error, StackTrace stackTrace) {
      if (!result.isCompleted) {
        result.completeError(error, stackTrace);
      }
    },
  );
  cancellation?.whenCancelled.then((_) {
    if (!result.isCompleted) {
      result.completeError(
        const CloudOperationCancelledException(),
        StackTrace.current,
      );
    }
  });
  if (deadlineAt != null) {
    final remaining = deadlineAt.difference(clock());
    if (remaining <= Duration.zero) {
      if (!result.isCompleted) {
        result.completeError(
          TimeoutException('Cloud operation prerequisite deadline exhausted'),
          StackTrace.current,
        );
      }
    } else {
      deadlineTimer = Timer(remaining, () {
        if (!result.isCompleted) {
          result.completeError(
            TimeoutException('Cloud operation prerequisite deadline exhausted'),
            StackTrace.current,
          );
        }
      });
    }
  }

  try {
    return await result.future;
  } finally {
    deadlineTimer?.cancel();
  }
}
