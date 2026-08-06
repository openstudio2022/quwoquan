import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleBehaviorFactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteCircleBehaviorFactWriter
    implements CircleBehaviorFactAppender {
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
