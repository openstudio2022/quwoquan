import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostReactionInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Post ContentReaction 的 production Remote；operation、path、codec 与 retry
/// 均由 generated client / Runtime executor 持有。
final class RemoteContentPostReactionFacet implements ContentPostReactionFacet {
  const RemoteContentPostReactionFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentPostReactionInvocationContextFactory invocationContext;

  @override
  Future<ContentReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  ) => client.contentContentReactionGetContentReactionState(
    query,
    context: invocationContext(
      ContentRequestPageIds.getContentReactionState,
      command: false,
    ),
  );

  @override
  Future<ContentReactionCommandResult> likePost(
    LikeContentPostCommand command,
  ) => client.contentContentReactionLikePost(
    command,
    context: invocationContext(ContentRequestPageIds.likePost, command: true),
  );

  @override
  Future<ContentReactionCommandResult> unlikePost(
    UnlikeContentPostCommand command,
  ) => client.contentContentReactionUnlikePost(
    command,
    context: invocationContext(ContentRequestPageIds.unlikePost, command: true),
  );
}
