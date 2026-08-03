// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_subscription_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'SkillSubscription generated adapter owns all public runtime paths',
    () async {
      final requests = <http.Request>[];
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requests.add(request);
          final response =
              request.method == 'GET' &&
                  request.url.path == '/assistant/skill-subscriptions'
              ? <String, Object?>{
                  'items': <Object?>[_subscriptionResponse()],
                }
              : _subscriptionResponse(
                  status: request.method == 'PATCH' ? 'paused' : 'active',
                );
          return http.Response(
            jsonEncode(response),
            200,
            request: request,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _AssistantSubscriptionAuthTokenProvider(),
      );
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _AssistantSubscriptionClientContext(),
        telemetrySink: const _AssistantSubscriptionTelemetrySink(),
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://assistant.test'),
        ),
      );
      final adapter = RemoteAssistantSkillSubscriptionAdapter(
        client: client,
        invocationContext: (clientPageId, {idempotencyKey}) =>
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

      final listed = await adapter.listSkillSubscriptions(status: 'active');
      final fetched = await adapter.getSkillSubscription(
        subscriptionId: 'subscription-1',
      );
      final created = await adapter.createSkillSubscription(
        skillId: 'daily_digest',
        rawText: 'daily digest',
        clientRequestId: 'create-intent-1',
      );
      final updated = await adapter.updateSkillSubscriptionStatus(
        subscriptionId: 'subscription-1',
        status: 'paused',
        clientRequestId: 'update-intent-1',
      );

      expect(listed.single.subscriptionId, 'subscription-1');
      expect(fetched.owner.ownerId, 'account-1');
      expect(created.searchQueryPlan.queries, <String>['daily digest']);
      expect(updated.status.name, 'paused');
      expect(requests.map((request) => request.url.path), <String>[
        '/assistant/skill-subscriptions',
        '/assistant/skill-subscriptions/subscription-1',
        '/assistant/skill-subscriptions',
        '/assistant/skill-subscriptions/subscription-1/status',
      ]);
      expect(requests[2].headers['Idempotency-Key'], 'create-intent-1');
      expect(requests[3].headers['Idempotency-Key'], 'update-intent-1');
      expect(
        (jsonDecode(requests[2].body)
            as Map<String, dynamic>)['clientRequestId'],
        'create-intent-1',
      );
      expect(
        ((jsonDecode(requests[2].body) as Map<String, dynamic>)['trigger']
            as Map<String, dynamic>)['timezone'],
        'Asia/Shanghai',
      );
    },
  );
}

Map<String, Object?> _subscriptionResponse({String status = 'active'}) {
  return <String, Object?>{
    'subscriptionId': 'subscription-1',
    'version': 1,
    'owner': <String, Object?>{'ownerType': 'user', 'ownerId': 'account-1'},
    'createdByUserId': 'account-1',
    'createdByPersonaId': 'persona-1',
    'skillId': 'daily_digest',
    'domainId': 'assistant',
    'tagRefs': <String>['travel'],
    'status': status,
    'searchQueryPlan': <String, Object?>{
      'rawText': 'daily digest',
      'queries': <String>['daily digest'],
    },
    'trigger': <String, Object?>{
      'type': 'cron',
      'cron': '0 8 * * *',
      'timezone': 'Asia/Shanghai',
    },
    'destination': <String, Object?>{
      'destinationType': 'user',
      'destinationId': 'account-1',
      'maxPerDay': 1,
      'cooldownMinutes': 60,
      'quietHoursPolicy': 'inherit_user_setting',
    },
    'deliveryState': <String, Object?>{
      'pendingDeliveryId': null,
      'lastAttemptAt': null,
      'lastDeliveredAt': null,
      'nextAttemptAt': null,
      'consecutiveFailures': 0,
      'lastErrorCode': null,
    },
    'createdAt': '2026-07-26T09:00:00Z',
    'updatedAt': '2026-07-26T09:00:00Z',
  };
}

final class _AssistantSubscriptionAuthTokenProvider
    implements CloudAuthTokenProvider {
  const _AssistantSubscriptionAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-test-token';
}

final class _AssistantSubscriptionClientContext
    implements CloudClientContextProvider {
  const _AssistantSubscriptionClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'assistant-subscription-test',
      platform: 'ios',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _AssistantSubscriptionTelemetrySink
    implements CloudOperationTelemetrySink {
  const _AssistantSubscriptionTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
