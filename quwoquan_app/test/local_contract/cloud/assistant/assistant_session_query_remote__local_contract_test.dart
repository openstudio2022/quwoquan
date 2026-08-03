import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

import '../../../support/assistant_remote_test_support.dart';

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
      final repository = RemoteAssistantRepository(
        operationClient: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
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
