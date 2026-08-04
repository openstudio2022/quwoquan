// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

import '../../../support/assistant_remote_test_support.dart';

void main() {
  test(
    'network Assistant surface never advertises media or action nodes',
    () async {
      final transport = _NetworkAssistantClient();
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
      );
      final repository = RemoteAssistantRepository(
        operationClient: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      final snapshot = await repository.executeAssistantSearch(
        query: '杭州路线',
        sessionClientRequestId: 'network-session-request',
        runClientRequestId: 'network-run-request',
      );

      expect(snapshot.answerText, 'network answer');
      final startRequest = transport.requests.singleWhere(
        (request) => request.url.path.endsWith('/runs'),
      );
      final body =
          jsonDecode((startRequest as http.Request).body)
              as Map<String, dynamic>;
      final capabilities = body['surfaceCapabilities'] as Map<String, dynamic>;
      final nodeKinds = (capabilities['supportedNodeKinds'] as List<dynamic>)
          .cast<String>();
      expect(capabilities, containsPair('viewportClass', 'standard'));
      expect(nodeKinds, isEmpty);
    },
  );
}

final class _NetworkAssistantClient extends http.BaseClient {
  final List<http.BaseRequest> requests = <http.BaseRequest>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    final path = request.url.path;
    if (path == '/assistant/sessions') {
      return _json(request, <String, Object?>{
        'sessionId': 'session-network',
        'userId': 'user-network',
        'state': 'active',
        'activeTurnId': '',
        'lastTurnId': '',
        'summary': '杭州路线',
        'createdAt': '2026-08-04T00:00:00Z',
        'updatedAt': '2026-08-04T00:00:00Z',
      }, statusCode: 201);
    }
    if (path == '/assistant/sessions/session-network/runs') {
      return _json(request, _run(status: 'queued'), statusCode: 201);
    }
    if (path == '/assistant/runs/run-network/events') {
      final event = <String, Object?>{
        'schema': 'assistant_stream_event',
        'eventId': 'event-network-completed',
        'sessionId': 'session-network',
        'runId': 'run-network',
        'seq': 1,
        'eventType': 'completed',
        'traceId': 'trace-network',
        'payload': const <String, Object?>{'status': 'completed'},
        'createdAt': '2026-08-04T00:00:02Z',
      };
      final frame =
          'id: resume-network\n'
          'event: completed\n'
          'data: ${jsonEncode(event)}\n\n';
      return http.StreamedResponse(
        Stream<List<int>>.value(utf8.encode(frame)),
        200,
        request: request,
        headers: const <String, String>{'content-type': 'text/event-stream'},
      );
    }
    if (path == '/assistant/runs/run-network') {
      return _json(request, _run(status: 'completed', terminal: true));
    }
    throw StateError('unexpected network Assistant request: $path');
  }

  Map<String, Object?> _run({required String status, bool terminal = false}) {
    return <String, Object?>{
      'runId': 'run-network',
      'sessionId': 'session-network',
      'status': status,
      'goal': '杭州路线',
      'streamState': const <String, Object?>{},
      'createdAt': '2026-08-04T00:00:01Z',
      if (terminal)
        'terminalSnapshot': const <String, Object?>{
          'answerText': 'network answer',
          'processes': <Object?>[],
        },
    };
  }

  http.StreamedResponse _json(
    http.BaseRequest request,
    Map<String, Object?> body, {
    int statusCode = 200,
  }) {
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode(jsonEncode(body))),
      statusCode,
      request: request,
      headers: const <String, String>{'content-type': 'application/json'},
    );
  }
}
