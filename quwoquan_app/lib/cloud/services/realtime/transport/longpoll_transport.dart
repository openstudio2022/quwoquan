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
  static const _maxConsecutiveErrors = 5;

  void start() {
    if (_running || _disposed) return;
    _running = true;
    _poll();
  }

  void stop() {
    _running = false;
  }

  Future<void> _poll() async {
    while (_running && !_disposed) {
      try {
        final credential = await RealtimeConnectionCredential.resolveHttp(
          authTokenProvider,
        );
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

        if (!_running || _disposed) break;

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
        _consecutiveErrors++;
        if (kDebugMode) {
          debugPrint('LongPollTransport: request failed');
        }
      }

      if (_consecutiveErrors >= _maxConsecutiveErrors) {
        final backoff = Duration(
          seconds: (_consecutiveErrors - _maxConsecutiveErrors + 1).clamp(
            5,
            30,
          ),
        );
        await Future<void>.delayed(backoff);
      }
    }
  }

  void dispose() {
    _disposed = true;
    _running = false;
    if (_ownsClient) {
      _client.close();
    }
  }
}
