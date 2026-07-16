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
