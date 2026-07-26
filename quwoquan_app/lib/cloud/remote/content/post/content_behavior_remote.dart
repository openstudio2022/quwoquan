import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentBehaviorInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteContentBehaviorCommandAdapter
    implements ContentBehaviorCommandWriter {
  const RemoteContentBehaviorCommandAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentBehaviorInvocationContextFactory invocationContext;

  @override
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command) {
    return client.contentPostReportBehaviors(
      command,
      context: invocationContext(ContentRequestPageIds.reportBehaviors),
    );
  }
}
