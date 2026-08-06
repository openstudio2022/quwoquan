// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/adapters/assistant_learning_fact_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test(
    'assistant learning fact command carries matching body and idempotency identity',
    () async {
      final transport = AssistantRecordingCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'eventId': 'feedback:turn-1:useful',
          'accepted': true,
          'deduplicated': false,
          'appendSequence': 7,
          'payloadDigest':
              '0000000000000000000000000000000000000000000000000000000000000000',
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
      final request = AssistantLearningFactAppendCommand(
        eventId: 'feedback:turn-1:useful',
        factType: AssistantLearningFactType.userFeedback.wireName,
        assistantTurnId: 'turn-1',
        referralSource: AssistantReferralSource.assistantSession.wireName,
        domainId: 'assistant',
        feedbackType: FeedbackType.useful.wireName,
        actionType: 'useful',
        trainingEligible: false,
        occurredAt: DateTime.utc(2026, 7, 26, 9),
      );

      final receipt = await repository.appendUserFact(request: request);

      expect(receipt.accepted, isTrue);
      expect(receipt.eventId, request.eventId);
      final outbound = transport.requests.single;
      final body = jsonDecode(outbound.body) as Map<String, dynamic>;
      expect(outbound.url.path, '/assistant/learning/facts');
      expect(outbound.headers['Idempotency-Key'], request.eventId);
      expect(body['eventId'], request.eventId);
      expect(body['factType'], 'user_feedback');
      expect(body['assistantTurnId'], request.assistantTurnId);
      expect(body['referralSource'], 'assistant_session');
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
