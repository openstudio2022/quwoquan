// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// readiness_case: assistant_session_create_assistant_session_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/adapters/assistant_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test(
    'CreateAssistantSession uses canonical generated command identity',
    () async {
      final transport = AssistantRecordingCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'sessionId': 'session-1',
          'userId': 'account-1',
          'state': 'active',
          'activeTurnId': '',
          'lastTurnId': '',
          'summary': '新会话',
          'createdAt': '2026-08-08T10:00:00Z',
          'updatedAt': '2026-08-08T10:00:00Z',
        },
      ]);
      final remote = AssistantSessionGeneratedAdapter(
        client: buildAssistantRemoteTestOperationClient(
          CloudHttpClient(
            client: transport,
            authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
          ),
        ),
        invocationContext: assistantRemoteTestInvocationContext,
      );

      final session = await remote.createAssistantSession(
        summary: '  新会话  ',
        clientRequestId: 'session-intent-1',
      );

      expect(transport.requests, hasLength(1));
      final request = transport.requests.single;
      expect(request.method, 'POST');
      expect(request.url.path, '/assistant/sessions');
      expect(
        request.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.assistantAssistantSessionCreateAssistantSession,
      );
      expect(request.headers['Idempotency-Key'], 'session-intent-1');
      expect(request.headers['Authorization'], 'Bearer assistant-test-token');
      expect(jsonDecode(request.body), <String, Object?>{
        'summary': '新会话',
        'clientRequestId': 'session-intent-1',
      });
      expect(session.sessionId, 'session-1');
      expect(session.summary, '新会话');
      expect(session.state, 'active');
    },
  );

  test('blank client request identity fails before transport', () async {
    final transport = AssistantRecordingCommandClient(
      const <Map<String, Object?>>[],
    );
    final remote = AssistantSessionGeneratedAdapter(
      client: buildAssistantRemoteTestOperationClient(
        CloudHttpClient(
          client: transport,
          authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
        ),
      ),
      invocationContext: assistantRemoteTestInvocationContext,
    );

    await expectLater(
      remote.createAssistantSession(clientRequestId: '  '),
      throwsArgumentError,
    );
    expect(transport.requests, isEmpty);
  });
}
