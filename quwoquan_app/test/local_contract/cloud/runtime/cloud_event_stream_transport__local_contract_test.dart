// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_json_transport.dart';

void main() {
  test(
    'SSE transport preserves protocol eventId and decodes multiline data',
    () async {
      final transport = HttpCloudJsonTransport(
        CloudHttpClient(client: _SseFrameClient()),
      );
      final frames = await transport
          .stream(
            CloudJsonTransportRequest(
              method: 'GET',
              authMode: 'public',
              uri: Uri.parse('https://assistant.test/runs/run-1/events'),
              gatewayOrigin: Uri.parse('https://assistant.test'),
              headers: const <String, String>{},
              abortTrigger: Completer<void>().future,
              maximumResponseBodyBytes: 4096,
            ),
          )
          .toList();

      expect(frames, hasLength(1));
      expect(frames.single.eventId, 'opaque-resume-token');
      expect(frames.single.data, <String, Object?>{
        'eventId': 'business-event-1',
        'eventType': 'completed',
      });
    },
  );
}

final class _SseFrameClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final payload = utf8.encode(
      ': heartbeat\r\n\r\n'
      'id: opaque-resume-token\r\n'
      'event: completed\r\n'
      'data: {"eventId":"business-event-1",\r\n'
      'data: "eventType":"completed"}\r\n\r\n',
    );
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable(<List<int>>[
        payload.sublist(0, 11),
        payload.sublist(11),
      ]),
      200,
      request: request,
      headers: const <String, String>{'content-type': 'text/event-stream'},
    );
  }
}
