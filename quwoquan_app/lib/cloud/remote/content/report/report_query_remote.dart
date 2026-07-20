import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ReportQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteContentReportQueryAdapter
    implements ContentMyReportQueryFacet {
  const RemoteContentReportQueryAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ReportQueryInvocationContextFactory invocationContext;

  @override
  Future<ContentMyReportPage> listMyReports(ContentMyReportsQuery query) {
    return client.contentReportListMyReports(
      query,
      context: invocationContext(ContentRequestPageIds.listMyReports),
    );
  }
}
