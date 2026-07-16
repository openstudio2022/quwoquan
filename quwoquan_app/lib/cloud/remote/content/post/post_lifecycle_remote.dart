import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostLifecycleInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Production-only Post lifecycle Remote。所有调用固定经过 generated client。
final class RemoteContentPostLifecycleCommandWriter
    implements ContentPostLifecycleCommandWriter {
  const RemoteContentPostLifecycleCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentPostLifecycleInvocationContextFactory invocationContext;

  @override
  Future<ContentPostLifecycleCommandResult> createPost(
    CreateContentPostCommand command,
  ) => client.contentPostCreatePost(
    command,
    context: invocationContext(ContentRequestPageIds.createPost),
  );

  @override
  Future<ContentPostLifecycleCommandResult> publishPost(
    PublishContentPostCommand command,
  ) => client.contentPostPublishPost(
    command,
    context: invocationContext(ContentRequestPageIds.publishPost),
  );
}
