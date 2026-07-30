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

/// Callback for incoming realtime events from long-polling.
typedef LongPollEventCallback =
    void Function(List<Map<String, dynamic>> events);

/// Long-polling transport for idle (app foreground, no active chat) state.
/// Polls `GET /chat/realtime/poll` with long-hold semantics.
class LongPollTransport {
  LongPollTransport({
    required this.config,
    required this.authTokenProvider,
    required this.onEvents,
    http.Client? client,
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null;

  final RealtimeConfig config;
  final CloudAuthTokenProvider authTokenProvider;
  final LongPollEventCallback onEvents;
  final http.Client _client;
  final bool _ownsClient;

  bool _running = false;
  bool _disposed = false;
  int _consecutiveErrors = 0;
  int _pollGeneration = 0;
  Timer? _backoffTimer;
  Completer<void>? _backoffCompleter;
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
        final url =
            Uri.parse(
              '${config.gatewayBaseUrl}${RealtimeApiMetadata.longPollPath}',
            ).replace(
              queryParameters: <String, String>{
                'timeout': '${config.longPollHoldSec}',
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
          if (body is Map && body['events'] is List) {
            final events = (body['events'] as List)
                .whereType<Map<String, dynamic>>()
                .toList();
            if (events.isNotEmpty) onEvents(events);
          }
        } else if (resp.statusCode == 204) {
          _consecutiveErrors = 0;
        } else if (resp.statusCode == 401 || resp.statusCode == 403) {
          _running = false;
          break;
        } else {
          _consecutiveErrors++;
        }
      } catch (_) {
        if (!_running || _disposed || generation != _pollGeneration) break;
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
