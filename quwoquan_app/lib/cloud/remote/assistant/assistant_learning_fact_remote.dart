import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantLearningFactInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required String idempotencyKey,
    });

/// AssistantLearningFact 的 production generated-client append adapter。
final class RemoteAssistantLearningFactAppendAdapter
    implements AssistantLearningFactAppendFacet {
  const RemoteAssistantLearningFactAppendAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantLearningFactInvocationContextFactory invocationContext;

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AppendAssistantLearningFactRequest request,
  }) async {
    final eventId = request.eventId.trim();
    if (eventId.isEmpty) {
      throw ArgumentError.value(
        request.eventId,
        'request.eventId',
        'AppendAssistantLearningFact requires a stable event identity',
      );
    }
    // dart format off
    final receipt = await client.assistantAssistantLearningFactAppendAssistantLearningFact(
          AssistantLearningFactAppendCommand(
            eventId: eventId,
            eventVersion: request.eventVersion,
            factType: request.factType.wireName,
            assistantTurnId: request.assistantTurnId,
            triggerMessageId: request.triggerMessageId,
            referralSource: request.referralSource.wireName,
            domainId: request.domainId,
            eventType: request.eventType?.wireName,
            feedbackType: request.feedbackType?.wireName,
            feedbackScore: request.feedbackScore,
            reasonCodes: request.reasonCodes ?? const <String>[],
            actionType: request.actionType,
            suggestedActionId: request.suggestedActionId,
            durationMs: request.durationMs,
            queryText: request.queryText,
            answerText: request.answerText,
            feedbackText: request.feedbackText,
            correctionText: request.correctionText,
            trainingEligible: request.trainingEligible,
            occurredAt: _requiredTimestamp(request.occurredAt),
          ),
          context: invocationContext(
            AssistantRequestPageIds.appendAssistantLearningFact,
            idempotencyKey: eventId,
          ),
        );
    // dart format on
    return AssistantLearningFactReceipt(
      eventId: receipt.eventId,
      eventVersion: receipt.eventVersion,
      accepted: receipt.accepted,
      deduplicated: receipt.deduplicated,
      appendSequence: receipt.appendSequence,
      payloadDigest: receipt.payloadDigest,
      recordedAt: receipt.recordedAt.toIso8601String(),
    );
  }
}

DateTime _requiredTimestamp(String? value) {
  final parsed = DateTime.tryParse(value?.trim() ?? '');
  if (parsed == null) {
    throw ArgumentError.value(value, 'occurredAt', 'must be ISO-8601');
  }
  return parsed.toUtc();
}
