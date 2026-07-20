import 'package:quwoquan_app/cloud/runtime/generated/tag/tag_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TagInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// TagFeedback 的 production Remote append writer。
/// path/auth/Idempotency-Key/decoder 由 generated client/executor 承担。
final class RemoteTagFeedbackAdapter implements TagFeedbackCommandWriter {
  const RemoteTagFeedbackAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TagInvocationContextFactory invocationContext;

  @override
  Future<TagFeedbackAck> reportTagFeedback(ReportTagFeedbackCommand command) {
    return client.tagTagFeedbackReportTagFeedback(
      command,
      context: invocationContext(TagRequestPageIds.reportTagFeedback),
    );
  }
}
