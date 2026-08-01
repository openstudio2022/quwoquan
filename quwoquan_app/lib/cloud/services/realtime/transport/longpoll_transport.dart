import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';
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
    required this.onEvents,
    this._cursorStore = const SharedPreferencesLongPollCursorStore(),
    http.Client? client,
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null;

  final RealtimeConfig config;
  final CloudAuthTokenProvider authTokenProvider;
  final LongPollEventCallback onEvents;
  final LongPollCursorStore _cursorStore;
  final http.Client _client;
  final bool _ownsClient;

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
        final url =
            Uri.parse(
              '${config.gatewayBaseUrl}${RealtimeApiMetadata.longPollPath}',
            ).replace(
              queryParameters: <String, String>{
                'timeout': '${config.longPollHoldSec}',
                'cursor': ?_cursor,
              },
            );
        final headers = credential.authorizeHttp(
          CloudRequestHeaders.forPage(RealtimeRequestPageIds.longPoll),
        );
        final resp = await _client
            .get(url, headers: headers)
            .timeout(Duration(seconds: config.longPollHoldSec + 10));

        if (!_running || _disposed || generation != _pollGeneration) break;

        if (resp.statusCode == 200) {
          _consecutiveErrors = 0;
          final body = jsonDecode(resp.body);
          if (body is! Map || body['events'] is! List) {
            throw const FormatException('invalid long poll response envelope');
          }
          final nextCursor = (body['nextCursor'] as String?)?.trim() ?? '';
          if (!_isCanonicalCursor(nextCursor)) {
            throw const FormatException('invalid long poll nextCursor');
          }
          final events = (body['events'] as List)
              .whereType<Map<String, dynamic>>()
              .toList();
          final partition = _cursorPartition;
          if (partition == null) {
            throw StateError('long poll cursor partition is unavailable');
          }
          await _cursorStore.write(partition, nextCursor);
          _cursor = nextCursor;
          if (body['transportResumed'] == true && !_resumeRecoveryEmitted) {
            _resumeRecoveryEmitted = true;
            onEvents(const <Map<String, dynamic>>[
              <String, dynamic>{'type': 'Reconnected'},
            ]);
          }
          if (events.isNotEmpty) onEvents(events);
        } else if (resp.statusCode == 204) {
          _consecutiveErrors = 0;
        } else if (resp.statusCode == 401 || resp.statusCode == 403) {
          _running = false;
          break;
        } else {
          _reportFirstFailure('http_${resp.statusCode}');
          _consecutiveErrors++;
        }
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
    if (_ownsClient) {
      _client.close();
    }
  }
}
