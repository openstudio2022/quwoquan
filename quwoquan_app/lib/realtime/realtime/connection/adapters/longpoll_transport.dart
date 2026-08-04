import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/realtime/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/realtime/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Callback for incoming realtime events from long-polling.
typedef LongPollEventCallback =
    void Function(List<Map<String, dynamic>> events);

typedef LongPollFirstFailureCallback = void Function(String reasonCode);

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
    required this.onEvents,
    this._cursorStore = const SharedPreferencesLongPollCursorStore(),
  });

  final RealtimeConfig config;
  final CloudAuthTokenProvider authTokenProvider;
  final RealtimeConnectionOperationGateway? operations;
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
        await _loadCursor(credential.cursorPartition);
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

        _consecutiveErrors = 0;
        final nextCursor = response.nextCursor.trim();
        if (!_isCanonicalCursor(nextCursor)) {
          throw const FormatException('invalid long poll nextCursor');
        }
        final events = response.events
            .map((event) => Map<String, dynamic>.from(event.toWire()))
            .toList(growable: false);
        final partition = _cursorPartition;
        if (partition == null) {
          throw StateError('long poll cursor partition is unavailable');
        }
        await _cursorStore.write(partition, nextCursor);
        _cursor = nextCursor;
        if (response.transportResumed && !_resumeRecoveryEmitted) {
          _resumeRecoveryEmitted = true;
          onEvents(const <Map<String, dynamic>>[
            <String, dynamic>{'type': 'Reconnected'},
          ]);
        }
        if (events.isNotEmpty) onEvents(events);
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

  Future<void> _loadCursor(String partition) async {
    if (_cursorPartition == partition) return;
    final stored = (await _cursorStore.read(partition))?.trim();
    _cursorPartition = partition;
    _cursor = stored != null && _isCanonicalCursor(stored) ? stored : null;
    _resumeRecoveryEmitted = false;
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
