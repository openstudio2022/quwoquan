import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Callback for incoming realtime events from long-polling.
typedef LongPollEventCallback = FutureOr<void> Function(
  List<Map<String, dynamic>> events,
);

typedef LongPollFirstFailureCallback = void Function(String reasonCode);

typedef LongPollActiveConversationIdResolver = String? Function();

abstract interface class LongPollCursorStore {
  Future<String?> read(String partition);

  Future<void> write(String partition, String cursor);
}

final class SharedPreferencesLongPollCursorStore
    implements LongPollCursorStore {
  const SharedPreferencesLongPollCursorStore();

  static const _keyPrefix = 'realtime.long_poll.cursor.';

  @override
  Future<String?> read(String partition) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString('$_keyPrefix$partition');
  }

  @override
  Future<void> write(String partition, String cursor) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('$_keyPrefix$partition', cursor);
  }
}

/// Long-polling transport for idle (app foreground, no active chat) state.
/// Polls `GET /chat/realtime/poll` with long-hold semantics.
class LongPollTransport {
  LongPollTransport({
    required this.config,
    required this.authTokenProvider,
    this.operations,
    required this.activeConversationIdResolver,
    required this.onEvents,
    this._cursorStore = const SharedPreferencesLongPollCursorStore(),
  });

  final RealtimeConfig config;
  final CloudAuthTokenProvider authTokenProvider;
  final RealtimeConnectionOperationGateway? operations;
  final LongPollActiveConversationIdResolver activeConversationIdResolver;
  final LongPollEventCallback onEvents;
  final LongPollCursorStore _cursorStore;

  bool _running = false;
  bool _disposed = false;
  int _consecutiveErrors = 0;
  int _pollGeneration = 0;
  Timer? _backoffTimer;
  Completer<void>? _backoffCompleter;
  LongPollFirstFailureCallback? onFirstTransportFailure;
  String? _cursorPartition;
  String? _cursor;
  bool _resumeRecoveryEmitted = false;
  static const _maxConsecutiveErrors = 5;

  void start() {
    if (_running || _disposed) return;
    _running = true;
    final generation = ++_pollGeneration;
    unawaited(_poll(generation));
  }

  void stop() {
    _running = false;
    _pollGeneration++;
    _cancelBackoff();
  }

  Future<void> _poll(int generation) async {
    while (_running && !_disposed && generation == _pollGeneration) {
      try {
        final credential = await RealtimeConnectionCredential.resolveHttp(
          authTokenProvider,
        );
        if (!_running || _disposed || generation != _pollGeneration) break;
        if (credential == null) {
          _running = false;
          break;
        }
        final cursorLoaded = await _loadCursor(
          credential.cursorPartition,
          generation,
        );
        if (!cursorLoaded) break;
        final gateway = operations;
        if (gateway == null) {
          throw StateError(
            'long poll requires generated realtime operation gateway',
          );
        }
        final response = await gateway
            .longPoll(timeout: config.longPollHoldSec, cursor: _cursor)
            .timeout(Duration(seconds: config.longPollHoldSec + 10));

        if (!_running || _disposed || generation != _pollGeneration) break;

        final nextCursor = response.nextCursor.trim();
        if (!_isCanonicalCursor(nextCursor)) {
          throw const FormatException('invalid long poll nextCursor');
        }
        final events = response.events
            .map((event) => Map<String, dynamic>.from(event.toWire()))
            .toList(growable: false);
        if (response.transportResumed && !_resumeRecoveryEmitted) {
          final conversationId = activeConversationIdResolver()?.trim();
          await Future<void>.sync(
            () => onEvents(<Map<String, dynamic>>[
              <String, dynamic>{
                'type': 'Reconnected',
                if (conversationId != null && conversationId.isNotEmpty)
                  'conversationId': conversationId,
              },
            ]),
          );
          if (!_running || _disposed || generation != _pollGeneration) break;
          _resumeRecoveryEmitted = true;
        }
        if (events.isNotEmpty) {
          await Future<void>.sync(() => onEvents(events));
        }
        if (!_running || _disposed || generation != _pollGeneration) break;
        final partition = _cursorPartition;
        if (partition == null) {
          throw StateError('long poll cursor partition is unavailable');
        }
        // Commit only after recovery and event dispatch completed. A failed
        // downstream recovery must retry from the last committed cursor.
        await _cursorStore.write(partition, nextCursor);
        _cursor = nextCursor;
        _consecutiveErrors = 0;
      } catch (error) {
        if (!_running || _disposed || generation != _pollGeneration) break;
        _reportFirstFailure(error.runtimeType.toString());
        _consecutiveErrors++;
        if (kDebugMode) {
          debugPrint('LongPollTransport: request failed');
        }
      }

      if (!_running || _disposed || generation != _pollGeneration) break;
      if (_consecutiveErrors >= _maxConsecutiveErrors) {
        final backoff = Duration(
          seconds: (_consecutiveErrors - _maxConsecutiveErrors + 1).clamp(
            5,
            30,
          ),
        );
        await _waitForBackoff(backoff);
      }
    }
  }

  Future<bool> _loadCursor(String partition, int generation) async {
    if (!_running || _disposed || generation != _pollGeneration) return false;
    if (_cursorPartition == partition) return true;
    final stored = (await _cursorStore.read(partition))?.trim();
    if (!_running || _disposed || generation != _pollGeneration) return false;
    _cursorPartition = partition;
    _cursor = stored != null && _isCanonicalCursor(stored) ? stored : null;
    _resumeRecoveryEmitted = false;
    return true;
  }

  static bool _isCanonicalCursor(String value) {
    return RegExp(r'^\d+-\d+$').hasMatch(value);
  }

  void _reportFirstFailure(String reasonCode) {
    if (_consecutiveErrors != 0) return;
    onFirstTransportFailure?.call(reasonCode);
  }

  Future<void> _waitForBackoff(Duration duration) {
    _cancelBackoff();
    final completer = Completer<void>();
    _backoffCompleter = completer;
    _backoffTimer = Timer(duration, () {
      _backoffTimer = null;
      if (identical(_backoffCompleter, completer)) {
        _backoffCompleter = null;
      }
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    return completer.future;
  }

  void _cancelBackoff() {
    _backoffTimer?.cancel();
    _backoffTimer = null;
    final completer = _backoffCompleter;
    _backoffCompleter = null;
    if (completer != null && !completer.isCompleted) {
      completer.complete();
    }
  }

  void dispose() {
    _disposed = true;
    _running = false;
    _pollGeneration++;
    _cancelBackoff();
  }
}
