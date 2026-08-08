// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// readiness_case: assistant_entry_view_get_assistant_entry_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/adapters/assistant_entry_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'GetAssistantEntry uses exact query binding and typed response',
    () async {
      final executor = _AssistantEntryExecutor();
      bool? observedNetworkSurface;
      final remote = AssistantEntryGeneratedAdapter(
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
                surfaceId: 'assistant.entry',
                clientPageId: clientPageId,
                actor: const CloudOperationActorContext(
                  accountId: 'account-1',
                  personaId: 'persona-1',
                ),
              );
            },
      );

      final entry = await remote.getAssistantEntry(
        context: const AssistantOpenContext(
          source: AssistantSource.profile,
          experienceLevel: AssistantExperienceLevel.returning,
          entityId: 'persona-2',
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.assistantAssistantEntryViewGetAssistantEntry,
      );
      expect(executor.operation?.method, 'GET');
      expect(executor.operation?.pathTemplate, '/assistant/entry');
      expect(
        executor.context?.clientPageId,
        AssistantRequestPageIds.getAssistantEntry,
      );
      expect(executor.payload?.pathParameters, isEmpty);
      expect(executor.payload?.queryParameters, <String, String>{
        'pageType': 'profile',
        'objectId': 'persona-2',
      });
      expect(executor.payload?.body, isNull);
      expect(observedNetworkSurface, isFalse);
      expect(entry.welcomeMessage, '我可以帮你理解这个主页');
      expect(entry.suggestionLines, isNotEmpty);
      expect(entry.chips.single.chipId, 'explain-profile');
      expect(entry.actions.single.actionId, 'ask-assistant');
      expect(entry.personalized, isTrue);
    },
  );
}

final class _AssistantEntryExecutor implements CloudOperationExecutor {
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
      'welcomeMessage': '我可以帮你理解这个主页',
      'suggestionLines': <String>['概括主页内容'],
      'chips': <Object?>[
        <String, Object?>{
          'chipId': 'explain-profile',
          'label': '概括资料',
          'actionType': 'prompt',
          'value': '请概括这个主页',
        },
      ],
      'actions': <Object?>[
        <String, Object?>{
          'actionId': 'ask-assistant',
          'actionType': 'open_session',
          'label': '问小趣',
          'payload': <String, Object?>{'objectId': 'persona-2'},
        },
      ],
      'personalized': true,
    });
  }
}
