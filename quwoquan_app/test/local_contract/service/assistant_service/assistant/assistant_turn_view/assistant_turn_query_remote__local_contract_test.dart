// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// readiness_case: assistant_turn_view_list_session_turns_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/adapters/assistant_turn_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('ListSessionTurns normalizes exact path/query and typed page', () async {
    final executor = _AssistantTurnExecutor();
    bool? observedNetworkSurface;
    final remote = AssistantTurnQueryGeneratedAdapter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext:
          (
            clientPageId, {
            String? idempotencyKey,
            bool networkSurface = false,
          }) {
            expect(idempotencyKey, isNull);
            observedNetworkSurface = networkSurface;
            return CloudOperationInvocationContext(
              surfaceId: 'assistant.turns',
              clientPageId: clientPageId,
              actor: const CloudOperationActorContext(
                accountId: 'account-1',
                personaId: 'persona-1',
              ),
            );
          },
    );

    final page = await remote.listSessionTurns(
      sessionId: '  session-1  ',
      limit: 40,
      cursor: '  cursor-1  ',
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.assistantAssistantTurnViewListSessionTurns,
    );
    expect(executor.operation?.method, 'GET');
    expect(
      executor.operation?.pathTemplate,
      '/assistant/sessions/{sessionId}/turns',
    );
    expect(
      executor.context?.clientPageId,
      AssistantRequestPageIds.listSessionTurns,
    );
    expect(executor.payload?.pathParameters, <String, String>{
      'sessionId': 'session-1',
    });
    expect(executor.payload?.queryParameters, <String, String>{
      'limit': '40',
      'cursor': 'cursor-1',
    });
    expect(executor.payload?.body, isNull);
    expect(observedNetworkSurface, isFalse);
    expect(page.items.single.turnId, 'turn-1');
    expect(page.items.single.status, 'completed');
    expect(page.nextCursor, 'cursor-2');
  });

  test('blank sessionId fails before generated transport', () async {
    final executor = _AssistantTurnExecutor();
    final remote = AssistantTurnQueryGeneratedAdapter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext:
          (
            clientPageId, {
            String? idempotencyKey,
            bool networkSurface = false,
          }) => CloudOperationInvocationContext(
            surfaceId: 'assistant.turns',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              accountId: 'account-1',
              personaId: 'persona-1',
            ),
          ),
    );

    expect(() => remote.listSessionTurns(sessionId: '  '), throwsArgumentError);
    expect(executor.operation, isNull);
  });
}

final class _AssistantTurnExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? payload;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    payload = requestEncoder();
    return responseDecoder(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'turnId': 'turn-1',
          'sessionId': 'session-1',
          'status': 'completed',
          'inputText': '总结今天的行程',
          'skillId': 'travel_companion',
          'domainId': 'travel',
          'createdAt': '2026-08-08T10:00:00Z',
          'completedAt': '2026-08-08T10:00:05Z',
        },
      ],
      'nextCursor': 'cursor-2',
    });
  }
}
