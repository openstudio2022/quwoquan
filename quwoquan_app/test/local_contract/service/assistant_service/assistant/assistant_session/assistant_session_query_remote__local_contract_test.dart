// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// readiness_case: assistant_session_list_assistant_sessions_app_local
// readiness_case: assistant_session_get_assistant_session_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/di/assistant_dependencies.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test(
    'AssistantSession ready queries use the generated client only',
    () async {
      final requests = <http.Request>[];
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requests.add(request);
          final response = request.url.path == '/assistant/sessions'
              ? <String, Object?>{
                  'items': <Object?>[_sessionResponse()],
                  'nextCursor': 'cursor-2',
                }
              : _sessionResponse();
          return http.Response(
            jsonEncode(response),
            200,
            request: request,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _AssistantQueryAuthTokenProvider(),
      );
      final repository = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      final page = await repository.listAssistantSessions(
        limit: 40,
        cursor: 'cursor-1',
      );
      final item = await repository.getAssistantSession(sessionId: 'session-1');

      expect(page.items.single.sessionId, 'session-1');
      expect(page.nextCursor, 'cursor-2');
      expect(item.summary, '单轨会话');
      expect(requests, hasLength(2));
      expect(requests[0].url.path, '/assistant/sessions');
      expect(requests[0].url.queryParameters, <String, String>{
        'limit': '40',
        'cursor': 'cursor-1',
      });
      expect(
        requests[0].headers['X-Client-Operation-Id'],
        'assistant.assistant_session.ListAssistantSessions',
      );
      expect(requests[1].url.path, '/assistant/sessions/session-1');
      expect(
        requests[1].headers['X-Client-Operation-Id'],
        'assistant.assistant_session.GetAssistantSession',
      );
      expect(
        requests.map((request) => request.headers['Authorization']),
        everyElement('Bearer assistant-query-test-token'),
      );
    },
  );
}

Map<String, Object?> _sessionResponse() {
  return <String, Object?>{
    'sessionId': 'session-1',
    'userId': 'user-1',
    'state': 'active',
    'activeTurnId': '',
    'lastTurnId': 'turn-1',
    'summary': '单轨会话',
    'createdAt': '2026-07-28T00:00:00Z',
    'updatedAt': '2026-07-28T00:01:00Z',
  };
}

final class _AssistantQueryAuthTokenProvider implements CloudAuthTokenProvider {
  const _AssistantQueryAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-query-test-token';
}
