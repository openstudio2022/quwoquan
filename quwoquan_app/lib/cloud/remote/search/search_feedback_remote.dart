import 'dart:convert';

import 'package:crypto/crypto.dart';
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
    final base = invocationContext(SearchRequestPageIds.reportSearchFeedback);
    return client.searchSearchFeedbackFactReportSearchFeedback(
      command,
      context: CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        actor: base.actor,
        routeId: base.routeId,
        referralSource: base.referralSource,
        feedRequestId: base.feedRequestId,
        shareId: base.shareId,
        modelId: base.modelId,
        experimentBucket: base.experimentBucket,
        idempotencyKey: base.idempotencyKey ?? _feedbackIdempotencyKey(command),
        deadlineAt: base.deadlineAt,
        cancellation: base.cancellation,
      ),
    );
  }

  String _feedbackIdempotencyKey(ReportSearchFeedbackCommand command) {
    final canonicalIdentity = <String>[
      command.searchRequestId,
      command.eventType.wireValue,
      command.objectId ?? '',
    ].join('\u0000');
    return 'search-feedback-${sha256.convert(utf8.encode(canonicalIdentity))}';
  }
}
