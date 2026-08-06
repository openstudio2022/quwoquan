import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:typed_data';

import 'package:quwoquan_app/cloud/runtime/codec/cloud_json_background_decoder_native.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/cloud/runtime/codec/cloud_json_background_decoder_web.dart'
    as platform_decoder;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

/// JSON responses at or above this size are decoded away from the UI isolate
/// on native platforms. Smaller responses stay inline to avoid isolate setup
/// overhead. The web implementation yields once before decoding because Dart
/// worker isolates are unavailable through the runtime's pure-Dart API.
const int cloudJsonBackgroundDecodeThresholdBytes = 64 * 1024;

/// Caps simultaneously active native decode isolates across the shared HTTP
/// client path. Additional responses either enter an explicitly bounded FIFO
/// or fail admission; they never create an implicit unbounded queue.
const int cloudJsonMaxConcurrentBackgroundDecodes = 2;

enum CloudJsonDecodeExecution { inline, background }

typedef CloudInlineJsonDecoder = CloudHttpDecodedJson Function(Uint8List bytes);
typedef CloudBackgroundJsonDecoder =
    Future<CloudHttpDecodedJson> Function(Uint8List bytes);
typedef CloudJsonDecodeObserver =
    void Function(CloudJsonDecodeExecution execution, int byteLength);

/// Internal interruption signal used to retire a queued decode before it gets
/// an isolate slot. [CloudHttpClient] translates it to its canonical transport
/// abort, preserving operation cancellation/deadline classification.
final class CloudJsonDecodeAbortedException implements Exception {
  const CloudJsonDecodeAbortedException();
}

/// A remote body or local decode burst exceeded a hard admission boundary.
///
/// The transport maps this to the canonical invalid-response failure. The
/// [reason] is intentionally low-cardinality and never includes response data.
final class CloudJsonDecodeAdmissionException implements Exception {
  const CloudJsonDecodeAdmissionException(this.reason);

  final String reason;

  @override
  String toString() => 'CloudJsonDecodeAdmissionException($reason)';
}

/// Size-aware, concurrency-bounded JSON response decoder.
///
/// Production clients share [shared], so multiple authenticated/public HTTP
/// clients cannot independently create an unbounded number of decode isolates.
/// The shared fallback deliberately has no pending queue and no inferred body
/// cap; a canonical live-response policy must be injected before claiming the
/// streamed byte boundary is enabled in production.
final class CloudJsonBodyDecoder {
  CloudJsonBodyDecoder({
    this.backgroundThresholdBytes = cloudJsonBackgroundDecodeThresholdBytes,
    this.maxConcurrentBackgroundDecodes =
        cloudJsonMaxConcurrentBackgroundDecodes,
    this.maxResponseBytes,
    int? maxPendingBackgroundDecodes,
    int? maxQueuedBackgroundDecodeBytes,
    int? maxPhysicalBackgroundDecodes,
    CloudInlineJsonDecoder? inlineDecoder,
    CloudBackgroundJsonDecoder? backgroundDecoder,
    this.observer,
  }) : _inlineDecoder = inlineDecoder ?? _decodeJson,
       _backgroundDecoder = backgroundDecoder ?? _decodeJsonInBackground,
       maxPendingBackgroundDecodes = maxPendingBackgroundDecodes ?? 0,
       maxQueuedBackgroundDecodeBytes = maxQueuedBackgroundDecodeBytes ?? 0,
       // A cancelled native Future cannot be killed through the pure-Dart
       // decoder API. One bounded replacement generation per logical slot
       // prevents a stuck retired generation from blocking all later work,
       // while repeated cancellation still cannot create unbounded isolates.
       maxPhysicalBackgroundDecodes =
           maxPhysicalBackgroundDecodes ?? maxConcurrentBackgroundDecodes * 2 {
    if (backgroundThresholdBytes < 1) {
      throw ArgumentError.value(
        backgroundThresholdBytes,
        'backgroundThresholdBytes',
        'must be positive',
      );
    }
    if (maxConcurrentBackgroundDecodes < 1) {
      throw ArgumentError.value(
        maxConcurrentBackgroundDecodes,
        'maxConcurrentBackgroundDecodes',
        'must be positive',
      );
    }
    if (maxResponseBytes != null && maxResponseBytes! < 1) {
      throw ArgumentError.value(
        maxResponseBytes,
        'maxResponseBytes',
        'must be positive',
      );
    }
    if (this.maxPendingBackgroundDecodes < 0) {
      throw ArgumentError.value(
        this.maxPendingBackgroundDecodes,
        'maxPendingBackgroundDecodes',
        'must not be negative',
      );
    }
    if (this.maxQueuedBackgroundDecodeBytes < 0) {
      throw ArgumentError.value(
        this.maxQueuedBackgroundDecodeBytes,
        'maxQueuedBackgroundDecodeBytes',
        'must not be negative',
      );
    }
    if ((this.maxPendingBackgroundDecodes == 0) !=
        (this.maxQueuedBackgroundDecodeBytes == 0)) {
      throw ArgumentError(
        'pending task and queued byte limits must both be zero or both be positive',
      );
    }
    if (this.maxPhysicalBackgroundDecodes < maxConcurrentBackgroundDecodes) {
      throw ArgumentError.value(
        this.maxPhysicalBackgroundDecodes,
        'maxPhysicalBackgroundDecodes',
        'must be at least maxConcurrentBackgroundDecodes',
      );
    }
  }

  static final CloudJsonBodyDecoder shared = CloudJsonBodyDecoder();

  final int backgroundThresholdBytes;
  final int maxConcurrentBackgroundDecodes;

  /// Null means no canonical live-response byte budget has been injected.
  ///
  /// In that state the decoder still has bounded physical work and rejects all
  /// pending work, but the HTTP transport cannot claim pre-buffer byte
  /// admission. Production closure therefore depends on a canonical owner
  /// supplying this value rather than borrowing an unrelated cache budget.
  final int? maxResponseBytes;
  final int maxPendingBackgroundDecodes;
  final int maxQueuedBackgroundDecodeBytes;
  final int maxPhysicalBackgroundDecodes;
  final CloudInlineJsonDecoder _inlineDecoder;
  final CloudBackgroundJsonDecoder _backgroundDecoder;
  final CloudJsonDecodeObserver? observer;

  int? effectiveMaximumResponseBytes(int? operationMaximumResponseBytes) {
    if (operationMaximumResponseBytes != null &&
        operationMaximumResponseBytes < 1) {
      throw ArgumentError.value(
        operationMaximumResponseBytes,
        'operationMaximumResponseBytes',
        'must be positive',
      );
    }
    final sharedMaximum = maxResponseBytes;
    if (sharedMaximum == null) return operationMaximumResponseBytes;
    if (operationMaximumResponseBytes == null) return sharedMaximum;
    return sharedMaximum < operationMaximumResponseBytes
        ? sharedMaximum
        : operationMaximumResponseBytes;
  }

  final Queue<_PendingCloudJsonDecode> _pending =
      Queue<_PendingCloudJsonDecode>();
  int _activeLogicalBackgroundDecodes = 0;
  int _activePhysicalBackgroundDecodes = 0;
  int _queuedBackgroundDecodeBytes = 0;
  int _nextGeneration = 0;

  Future<CloudHttpDecodedJson> decode({
    required Uint8List bytes,
    Future<void>? abortTrigger,
    int? maximumResponseBytes,
  }) {
    final byteLength = bytes.length;
    final responseLimit = effectiveMaximumResponseBytes(maximumResponseBytes);
    if (responseLimit != null && byteLength > responseLimit) {
      return Future<CloudHttpDecodedJson>.error(
        const CloudJsonDecodeAdmissionException('response_body_too_large'),
      );
    }
    if (byteLength < backgroundThresholdBytes) {
      observer?.call(CloudJsonDecodeExecution.inline, byteLength);
      return Future<CloudHttpDecodedJson>.sync(() => _inlineDecoder(bytes));
    }

    observer?.call(CloudJsonDecodeExecution.background, byteLength);
    final task = _PendingCloudJsonDecode(bytes, generation: ++_nextGeneration);
    abortTrigger?.then(
      (_) => _abort(task),
      onError: (Object error, StackTrace stackTrace) {
        _abort(task, error: error, stackTrace: stackTrace);
      },
    );
    if (_canStartPhysicalDecode) {
      _start(task);
    } else if (_pending.length >= maxPendingBackgroundDecodes) {
      task.completer.completeError(
        const CloudJsonDecodeAdmissionException('pending_task_limit'),
      );
    } else if (byteLength >
        maxQueuedBackgroundDecodeBytes - _queuedBackgroundDecodeBytes) {
      task.completer.completeError(
        const CloudJsonDecodeAdmissionException('queued_byte_limit'),
      );
    } else {
      _pending.addLast(task);
      _queuedBackgroundDecodeBytes += byteLength;
    }
    return task.completer.future;
  }

  void _abort(
    _PendingCloudJsonDecode task, {
    Object error = const CloudJsonDecodeAbortedException(),
    StackTrace? stackTrace,
  }) {
    if (task.completer.isCompleted) return;
    task.aborted = true;
    task.acceptedGeneration = -1;
    if (!task.started) {
      if (_pending.remove(task)) {
        _queuedBackgroundDecodeBytes -= task.bytes.length;
      }
    } else if (task.logicalSlotHeld) {
      task.logicalSlotHeld = false;
      _activeLogicalBackgroundDecodes -= 1;
    }
    task.completer.completeError(error, stackTrace ?? StackTrace.current);
    _drain();
  }

  bool get _canStartPhysicalDecode =>
      _activeLogicalBackgroundDecodes < maxConcurrentBackgroundDecodes &&
      _activePhysicalBackgroundDecodes < maxPhysicalBackgroundDecodes;

  void _drain() {
    while (_canStartPhysicalDecode && _pending.isNotEmpty) {
      final task = _pending.removeFirst();
      _queuedBackgroundDecodeBytes -= task.bytes.length;
      if (task.aborted) continue;
      _start(task);
    }
  }

  void _start(_PendingCloudJsonDecode task) {
    task.started = true;
    task.logicalSlotHeld = true;
    _activeLogicalBackgroundDecodes += 1;
    _activePhysicalBackgroundDecodes += 1;
    final generation = task.generation;
    Future<CloudHttpDecodedJson>.sync(
      () => _backgroundDecoder(task.bytes),
    ).then(
      (decoded) {
        if (!task.completer.isCompleted &&
            task.acceptedGeneration == generation) {
          task.completer.complete(decoded);
        }
        _finishBackgroundDecode(task);
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!task.completer.isCompleted &&
            task.acceptedGeneration == generation) {
          task.completer.completeError(error, stackTrace);
        }
        _finishBackgroundDecode(task);
      },
    );
  }

  void _finishBackgroundDecode(_PendingCloudJsonDecode task) {
    _activePhysicalBackgroundDecodes -= 1;
    if (task.logicalSlotHeld) {
      task.logicalSlotHeld = false;
      _activeLogicalBackgroundDecodes -= 1;
    }
    _drain();
  }
}

final class _PendingCloudJsonDecode {
  _PendingCloudJsonDecode(this.bytes, {required this.generation})
    : acceptedGeneration = generation;

  final Uint8List bytes;
  final int generation;
  final Completer<CloudHttpDecodedJson> completer =
      Completer<CloudHttpDecodedJson>();
  int acceptedGeneration;
  bool started = false;
  bool aborted = false;
  bool logicalSlotHeld = false;
}

CloudHttpDecodedJson _decodeJson(Uint8List bytes) {
  return jsonDecode(utf8.decode(bytes));
}

Future<CloudHttpDecodedJson> _decodeJsonInBackground(Uint8List bytes) {
  return platform_decoder.decodeJsonInBackground(bytes);
}
