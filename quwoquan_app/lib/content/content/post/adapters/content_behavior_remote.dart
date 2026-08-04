import 'dart:convert';

import 'package:crypto/crypto.dart';
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
    final base = invocationContext(ContentRequestPageIds.reportBehaviors);
    return client.contentContentBehaviorFactReportBehaviors(
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
        idempotencyKey: _batchIdempotencyKey(command),
        deadlineAt: base.deadlineAt,
        cancellation: base.cancellation,
      ),
    );
  }

  String _batchIdempotencyKey(ReportContentBehaviorsCommand command) {
    final material = jsonEncode(command.toWire());
    return 'behavior-batch-${sha256.convert(utf8.encode(material))}';
  }
}
