import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

void main() {
  test('SSE 提前断开后携带 Last-Event-ID 续传且事件不重复', () async {
    final transport = _SequentialSseClient(<String>[
      _sseFrame(
        id: 'resume-token-1',
        seq: 1,
        eventType: 'answer_delta',
        payload: const <String, Object?>{'text': '第一段'},
      ),
      [
        _sseFrame(
          id: 'resume-token-2',
          seq: 2,
          eventType: 'completed',
          payload: const <String, Object?>{
            'status': 'completed',
            'finalAnswer': '完整回答',
          },
        ),
      ].join(),
    ]);
    final repository = RemoteAssistantRepository(
      httpClient: CloudHttpClient(client: transport),
      consentActorScope: 'assistant-stream-resume-test',
    );

    final events = await repository
        .watchAssistantRunEvents(runId: 'run-resume-test')
        .toList();

    expect(events.map((event) => event.seq), <int>[1, 2]);
    expect(events.map((event) => event.eventType), <String>[
      'answer_delta',
      'completed',
    ]);
    expect(transport.requests, hasLength(2));
    final resumed = transport.requests.last;
    expect(resumed.headers['Last-Event-ID'], 'resume-token-1');
    expect(resumed.url.queryParameters['resumeToken'], 'resume-token-1');
  });
}

String _sseFrame({
  required String id,
  required int seq,
  required String eventType,
  required Map<String, Object?> payload,
}) {
  final envelope = <String, Object?>{
    'schema': 'assistant_stream_event',
    'eventId': 'event-$seq',
    'conversationId': 'conversation-resume-test',
    'turnId': 'run-resume-test',
    'seq': seq,
    'eventType': eventType,
    'traceId': 'trace-resume-test',
    'payload': payload,
    'createdAt': '2026-07-20T12:00:00Z',
  };
  return 'id: $id\nevent: $eventType\ndata: ${jsonEncode(envelope)}\n\n';
}

final class _SequentialSseClient extends http.BaseClient {
  _SequentialSseClient(this._responses);

  final List<String> _responses;
  final List<http.BaseRequest> requests = <http.BaseRequest>[];
  var _nextResponse = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    if (_nextResponse >= _responses.length) {
      throw StateError('unexpected assistant SSE reconnect');
    }
    final body = utf8.encode(_responses[_nextResponse++]);
    return http.StreamedResponse(
      Stream<List<int>>.value(body),
      200,
      request: request,
      headers: const <String, String>{'content-type': 'text/event-stream'},
    );
  }
}
