import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'recent_search_remote.dart' show SearchInvocationContextFactory;

/// SearchFeedbackFact 的 production Remote append writer。
/// 事实按 (searchRequestId, eventType, objectId) 语义键服务端去重，重放安全。
final class RemoteSearchFeedbackAdapter implements SearchFeedbackCommandWriter {
  const RemoteSearchFeedbackAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final SearchInvocationContextFactory invocationContext;

  @override
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  ) {
    return client.searchQueryReportSearchFeedback(
      command,
      context: invocationContext(SearchRequestPageIds.reportSearchFeedback),
    );
  }
}
