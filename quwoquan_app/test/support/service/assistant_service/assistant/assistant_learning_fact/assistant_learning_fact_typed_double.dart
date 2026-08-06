import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_append_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class InMemoryAssistantLearningFactAppendFacet
    implements AssistantLearningFactAppendFacet {
  final List<AssistantLearningFactAppendCommand> appended =
      <AssistantLearningFactAppendCommand>[];

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    appended.add(request);
    return AssistantLearningFactReceipt(
      eventId: request.eventId,
      accepted: true,
      deduplicated: false,
      appendSequence: appended.length,
      payloadDigest:
          '0000000000000000000000000000000000000000000000000000000000000000',
      recordedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }
}
