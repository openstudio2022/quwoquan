// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

void main() {
  test(
    'assistant command body and Idempotency-Key share one stable identity',
    () async {
      final transport = _AssistantCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'conversationId': 'conversation-1',
          'userId': 'user-1',
          'createdAt': '2026-07-24T09:00:00Z',
          'updatedAt': '2026-07-24T09:00:00Z',
        },
        <String, Object?>{
          'turnId': 'turn-1',
          'conversationId': 'conversation-1',
          'createdAt': '2026-07-24T09:00:01Z',
        },
      ]);
      final repository = RemoteAssistantRepository(
        httpClient: CloudHttpClient(client: transport),
        consentActorScope: 'assistant-command-identity-test',
      );

      await repository.createAssistantConversation(
        summary: 'assistant test',
        clientRequestId: 'conversation-intent-1',
      );
      await repository.startAssistantRun(
        conversationId: 'conversation-1',
        text: 'help me plan today',
        clientRequestId: 'run-intent-1',
        domainId: 'assistant',
      );

      expect(transport.requests, hasLength(2));
      final create = transport.requests[0];
      final createBody = jsonDecode(create.body) as Map<String, dynamic>;
      expect(create.headers['Idempotency-Key'], 'conversation-intent-1');
      expect(createBody['clientRequestId'], 'conversation-intent-1');
      expect(createBody['summary'], 'assistant test');
      expect(create.headers['X-Client-Page-Id'], isNotEmpty);
      expect(create.headers['X-Client-Session-Id'], isNotEmpty);
      expect(create.headers['X-Client-Surface-Id'], isNotEmpty);
      expect(create.headers['X-Client-Route-Id'], isNotEmpty);
      expect(create.headers['X-Client-Operation-Id'], isNotEmpty);
      expect(create.headers['X-Trace-Id'], startsWith('APP.'));

      final start = transport.requests[1];
      final startBody = jsonDecode(start.body) as Map<String, dynamic>;
      expect(start.headers['Idempotency-Key'], 'run-intent-1');
      expect(startBody['clientRequestId'], 'run-intent-1');
      expect(startBody['input'], <String, dynamic>{
        'text': 'help me plan today',
      });
      expect(startBody['trigger'], <String, dynamic>{'type': 'user_message'});
      expect(startBody['domainId'], 'assistant');
      expect(start.headers['X-Client-Page-Id'], isNotEmpty);
      expect(start.headers['X-Client-Session-Id'], isNotEmpty);
      expect(start.headers['X-Client-Surface-Id'], isNotEmpty);
      expect(start.headers['X-Client-Route-Id'], isNotEmpty);
      expect(start.headers['X-Client-Operation-Id'], isNotEmpty);
      expect(start.headers['X-Trace-Id'], startsWith('APP.'));
    },
  );

  test('assistant command rejects an empty client request identity', () async {
    final transport = _AssistantCommandClient(const <Map<String, Object?>>[]);
    final repository = RemoteAssistantRepository(
      httpClient: CloudHttpClient(client: transport),
      consentActorScope: 'assistant-command-identity-test',
    );

    await expectLater(
      repository.createAssistantConversation(clientRequestId: ' '),
      throwsArgumentError,
    );
    expect(transport.requests, isEmpty);
  });
}

final class _AssistantCommandClient extends http.BaseClient {
  _AssistantCommandClient(this._responses);

  final List<Map<String, Object?>> _responses;
  final List<http.Request> requests = <http.Request>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request is! http.Request) {
      throw StateError(
        'assistant command transport requires HTTP request body',
      );
    }
    requests.add(request);
    if (_responses.isEmpty) {
      throw StateError('unexpected assistant command request');
    }
    final response = _responses.removeAt(0);
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode(jsonEncode(response))),
      201,
      request: request,
      headers: const <String, String>{'content-type': 'application/json'},
    );
  }
}
