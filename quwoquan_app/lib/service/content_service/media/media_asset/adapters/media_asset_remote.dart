import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef MediaAssetInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// MediaAsset 对象拥有的 generated client adapter。
final class RemoteContentMediaAssetAdapter
    implements
        ContentMediaAssetQuery,
        ContentMediaAssetCommandWriter,
        ContentMediaCoverCommandWriter {
  const RemoteContentMediaAssetAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final MediaAssetInvocationContextFactory invocationContext;

  @override
  Future<MediaAssetSlice> getMediaAsset(GetContentMediaAssetQuery query) =>
      client.contentMediaAssetGetMediaAsset(
        query,
        context: invocationContext(
          ContentRequestPageIds.getMediaAsset,
          command: false,
        ),
      );

  @override
  Future<MediaAssetDiscardResult> discardMediaAsset(
    DiscardContentMediaAssetCommand command,
    ContentMediaAssetCommandContext context,
  ) => client.contentMediaAssetDiscardMediaAsset(
    command,
    context: _commandContext(
      ContentRequestPageIds.discardMediaAsset,
      context.idempotencyKey,
    ),
  );

  @override
  Future<MediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) => client.contentMediaAssetSelectAutoVideoCover(
    command,
    context: _commandContext(
      ContentRequestPageIds.selectAutoVideoCover,
      context.idempotencyKey,
    ),
  );

  @override
  Future<MediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) => client.contentMediaAssetSelectManualVideoCover(
    command,
    context: _commandContext(
      ContentRequestPageIds.selectManualVideoCover,
      context.idempotencyKey,
    ),
  );

  CloudOperationInvocationContext _commandContext(
    String clientPageId,
    String idempotencyKey,
  ) {
    final base = invocationContext(clientPageId, command: true);
    return CloudOperationInvocationContext(
      surfaceId: base.surfaceId,
      clientPageId: base.clientPageId,
      routeId: base.routeId,
      referralSource: base.referralSource,
      feedRequestId: base.feedRequestId,
      shareId: base.shareId,
      modelId: base.modelId,
      experimentBucket: base.experimentBucket,
      actor: base.actor,
      idempotencyKey: idempotencyKey,
      deadlineAt: base.deadlineAt,
      cancellation: base.cancellation,
    );
  }
}
