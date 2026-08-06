import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ReportInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteContentReportAdapter implements ContentReportWriter {
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
