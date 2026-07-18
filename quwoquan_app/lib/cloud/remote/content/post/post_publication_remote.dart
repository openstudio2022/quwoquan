import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostPublicationInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

/// Production-only 原子发布 Remote。所有调用固定经过 generated client。
final class RemoteContentPostPublicationWriter
    implements ContentPostPublicationWriter {
  const RemoteContentPostPublicationWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentPostPublicationInvocationContextFactory invocationContext;

  @override
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) => client.contentPostSubmitPostPublication(
    command,
    context: invocationContext(
      ContentRequestPageIds.submitPostPublication,
      command.publishIntentId,
    ),
  );
}
