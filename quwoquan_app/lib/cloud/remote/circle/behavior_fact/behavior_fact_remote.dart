import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleBehaviorFactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteCircleBehaviorFactWriter implements CircleBehaviorFactWriter {
  const RemoteCircleBehaviorFactWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleBehaviorFactInvocationContextFactory invocationContext;

  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) =>
      client.circleCircleBehaviorFactReportCircleBehavior(
        command,
        context: invocationContext(CircleRequestPageIds.reportCircleBehavior),
      );
}
