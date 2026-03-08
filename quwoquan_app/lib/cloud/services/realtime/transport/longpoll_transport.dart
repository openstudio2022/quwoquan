import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';

/// Callback for incoming realtime events from long-polling.
typedef LongPollEventCallback = void Function(List<Map<String, dynamic>> events);

/// Long-polling transport for idle (app foreground, no active chat) state.
/// Polls `GET /v1/chat/realtime/poll` with long-hold semantics.
class LongPollTransport {
  LongPollTransport({
    required this.config,
    required this.userId,
    required this.onEvents,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final RealtimeConfig config;
  final String userId;
  final LongPollEventCallback onEvents;
  final http.Client _client;

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
        final url = Uri.parse(
          '${CloudRuntimeConfig.gatewayBaseUrl}${RealtimeApiMetadata.longPollPath}',
        ).replace(
          queryParameters: <String, String>{
            'userId': userId,
            'hold': '${config.longPollHoldSec}',
          },
        );
        final headers = CloudRequestHeaders.forPage(RealtimeRequestPageIds.longPoll);
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
        } else {
          _consecutiveErrors++;
        }
      } catch (e) {
        _consecutiveErrors++;
        debugPrint('LongPollTransport: error: $e');
      }

      if (_consecutiveErrors >= _maxConsecutiveErrors) {
        final backoff = Duration(
          seconds: (_consecutiveErrors - _maxConsecutiveErrors + 1).clamp(5, 30),
        );
        await Future<void>.delayed(backoff);
      }
    }
  }

  void dispose() {
    _disposed = true;
    _running = false;
  }
}
