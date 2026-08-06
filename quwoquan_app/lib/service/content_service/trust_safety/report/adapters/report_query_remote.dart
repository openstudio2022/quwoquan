import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ReportQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteContentReportQueryAdapter implements ContentMyReportsReader {
  const RemoteContentReportQueryAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ReportQueryInvocationContextFactory invocationContext;

  @override
  Future<MyReportPageSlice> listMyReports(ContentMyReportsQuery query) {
    return client.contentReportListMyReports(
      query,
      context: invocationContext(ContentRequestPageIds.listMyReports),
    );
  }
}
