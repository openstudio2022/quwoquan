// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_learning_fact_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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

  test(
    'assistant learning fact command carries matching body and idempotency identity',
    () async {
      final transport = _AssistantCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'eventId': 'feedback:turn-1:useful',
          'eventVersion': 1,
          'accepted': true,
          'deduplicated': false,
          'appendSequence': 7,
          'payloadDigest': 'digest-1',
          'recordedAt': '2026-07-26T09:00:00Z',
        },
      ]);
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const _AssistantTestAuthTokenProvider(),
      );
      final repository = RemoteAssistantLearningFactAppendAdapter(
        client: buildGeneratedCloudOperationClient(
          httpClient: httpClient,
          clientContextProvider: const _AssistantTestClientContext(),
          telemetrySink: const _AssistantTestTelemetrySink(),
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse('https://assistant.test'),
          ),
        ),
        invocationContext: (clientPageId, {required idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.personalAssistantDialog.id,
              routeId: AppUiSurfaces.personalAssistantDialog.routeId,
              clientPageId: clientPageId,
              actor: const CloudOperationActorContext(
                accountId: 'account-1',
                personaId: 'persona-1',
              ),
              idempotencyKey: idempotencyKey,
            ),
      );
      const request = AppendAssistantLearningFactRequest(
        eventId: 'feedback:turn-1:useful',
        eventVersion: 1,
        factType: AssistantLearningFactType.userFeedback,
        assistantTurnId: 'turn-1',
        referralSource: AssistantReferralSource.assistantConversation,
        domainId: 'assistant',
        feedbackType: FeedbackType.useful,
        actionType: 'useful',
        trainingEligible: false,
        occurredAt: '2026-07-26T09:00:00Z',
      );

      final receipt = await repository.appendUserFact(request: request);

      expect(receipt.accepted, isTrue);
      expect(receipt.eventId, request.eventId);
      expect(receipt.eventVersion, request.eventVersion);
      final outbound = transport.requests.single;
      final body = jsonDecode(outbound.body) as Map<String, dynamic>;
      expect(outbound.url.path, '/assistant/learning/facts');
      expect(outbound.headers['Idempotency-Key'], request.eventId);
      expect(body['eventId'], request.eventId);
      expect(body['eventVersion'], request.eventVersion);
      expect(body['factType'], 'user_feedback');
      expect(body['assistantTurnId'], request.assistantTurnId);
      expect(body['referralSource'], 'assistant_conversation');
      expect(body['feedbackType'], 'useful');
      expect(body['trainingEligible'], isFalse);
      expect(outbound.headers['X-Client-Operation-Id'], isNotEmpty);
      expect(outbound.headers['X-Client-Page-Id'], isNotEmpty);
      expect(outbound.headers['X-Client-Surface-Id'], isNotEmpty);
      expect(outbound.headers['X-Client-Route-Id'], isNotEmpty);
      expect(outbound.headers['X-Trace-Id'], startsWith('APP.'));
    },
  );
}

final class _AssistantTestAuthTokenProvider implements CloudAuthTokenProvider {
  const _AssistantTestAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-test-token';
}

final class _AssistantTestClientContext implements CloudClientContextProvider {
  const _AssistantTestClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'assistant-test-session',
      platform: 'ios',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _AssistantTestTelemetrySink implements CloudOperationTelemetrySink {
  const _AssistantTestTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
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
