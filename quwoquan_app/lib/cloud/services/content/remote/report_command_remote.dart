import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ReportInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteContentReportAdapter implements ContentReportCommandWriter {
  const RemoteContentReportAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ReportInvocationContextFactory invocationContext;

  @override
  Future<void> createReport(CreateContentReportCommand command) async {
    await client.contentReportCreateReport(
      command,
      context: invocationContext(ContentRequestPageIds.createReport),
    );
  }
}
