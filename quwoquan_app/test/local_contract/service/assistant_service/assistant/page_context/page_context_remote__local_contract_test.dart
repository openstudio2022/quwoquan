// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
// readiness_case: page_context_report_page_context_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/adapters/page_context_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('ReportPageContext sends only canonical structured grounding', () async {
    final executor = _PageContextExecutor(accepted: true);
    bool? observedNetworkSurface;
    final remote = PageContextGeneratedAdapter(
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
              surfaceId: 'assistant.page-context',
              clientPageId: clientPageId,
              actor: const CloudOperationActorContext(
                accountId: 'account-1',
                personaId: 'persona-1',
              ),
            );
          },
    );

    final receipt = await remote.reportPageContext(
      context: const AssistantOpenContext(
        source: AssistantSource.article,
        experienceLevel: AssistantExperienceLevel.returning,
        entityId: 'post-1',
        objectType: 'content.post',
      ),
      userAction: '  opened_detail  ',
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.assistantPageContextReportPageContext,
    );
    expect(executor.operation?.method, 'POST');
    expect(executor.operation?.pathTemplate, '/assistant/page-context');
    expect(
      executor.context?.clientPageId,
      AssistantRequestPageIds.reportPageContext,
    );
    expect(executor.payload?.pathParameters, isEmpty);
    expect(executor.payload?.queryParameters, isEmpty);
    final body = executor.payload?.body as Map<String, Object?>;
    expect(body.keys, <String>{'contextSnapshot'});
    final snapshot = body['contextSnapshot'] as Map<String, Object?>;
    expect(snapshot['capturedAt'], isA<String>());
    expect(snapshot['pageType'], 'article');
    expect(snapshot['pageObjects'], <Object?>[
      <String, Object?>{'objectTypeRef': 'content.post', 'objectId': 'post-1'},
    ]);
    expect(snapshot['userActions'], <Object?>[
      <String, Object?>{
        'actionType': 'opened_detail',
        'objectTypeRef': 'content.post',
        'objectId': 'post-1',
      },
    ]);
    expect(snapshot['consentGranted'], isTrue);
    expect(observedNetworkSurface, isFalse);
    expect(receipt.contextKey, 'page-context-1');
  });

  test('unaccepted typed receipt fails closed', () async {
    final remote = PageContextGeneratedAdapter(
      client: GeneratedCloudOperationClient(
        _PageContextExecutor(accepted: false),
      ),
      invocationContext:
          (
            clientPageId, {
            String? idempotencyKey,
            bool networkSurface = false,
          }) => CloudOperationInvocationContext(
            surfaceId: 'assistant.page-context',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              accountId: 'account-1',
              personaId: 'persona-1',
            ),
          ),
    );

    await expectLater(
      remote.reportPageContext(
        context: const AssistantOpenContext(
          source: AssistantSource.home,
          experienceLevel: AssistantExperienceLevel.firstTime,
        ),
      ),
      throwsFormatException,
    );
  });
}

final class _PageContextExecutor implements CloudOperationExecutor {
  _PageContextExecutor({required this.accepted});

  final bool accepted;
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
      'accepted': accepted,
      'contextKey': 'page-context-1',
      'expiresAt': '2026-08-08T10:05:00Z',
    });
  }
}
