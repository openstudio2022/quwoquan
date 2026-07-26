import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentMediaInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Production Media Remote. It only maps typed Facet calls to the generated
/// operation-specific client and owns no path, operation ID or decoder.
final class RemoteContentMediaFacet implements ContentMediaFacet {
  const RemoteContentMediaFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentMediaInvocationContextFactory invocationContext;

  @override
  Future<ContentMediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => client.contentMediaUploadSessionInitMediaUpload(
    command,
    context: _uploadCommandContext(
      ContentRequestPageIds.initMediaUpload,
      context,
    ),
  );

  @override
  Future<ContentMediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => client.contentMediaUploadSessionCompleteMediaUpload(
    command,
    context: _uploadCommandContext(
      ContentRequestPageIds.completeMediaUpload,
      context,
    ),
  );

  @override
  Future<ContentMediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => client.contentMediaUploadSessionAbortMediaUpload(
    command,
    context: _uploadCommandContext(
      ContentRequestPageIds.abortMediaUpload,
      context,
    ),
  );

  @override
  Future<ContentMediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) => client.contentMediaUploadSessionGetMediaUploadSession(
    query,
    context: invocationContext(
      ContentRequestPageIds.getMediaUploadSession,
      command: false,
    ),
  );

  @override
  Future<ContentMediaAssetSlice> getMediaAsset(
    GetContentMediaAssetQuery query,
  ) => client.contentMediaAssetGetMediaAsset(
    query,
    context: invocationContext(
      ContentRequestPageIds.getMediaAsset,
      command: false,
    ),
  );

  @override
  Future<ContentMediaAssetDiscardResult> discardMediaAsset(
    DiscardContentMediaAssetCommand command,
    ContentMediaAssetCommandContext context,
  ) => client.contentMediaAssetDiscardMediaAsset(
    command,
    context: _commandContext(
      ContentRequestPageIds.discardMediaAsset,
      idempotencyKey: context.idempotencyKey,
    ),
  );

  @override
  Future<ContentMediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => client.contentMediaOriginalAccessFactRequestOriginalImageAccess(
    command,
    context: invocationContext(
      ContentRequestPageIds.requestOriginalImageAccess,
      command: true,
    ),
  );

  @override
  Future<ContentMediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) => client.contentMediaAssetSelectAutoVideoCover(
    command,
    context: _commandContext(
      ContentRequestPageIds.selectAutoVideoCover,
      idempotencyKey: context.idempotencyKey,
    ),
  );

  @override
  Future<ContentMediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) => client.contentMediaAssetSelectManualVideoCover(
    command,
    context: _commandContext(
      ContentRequestPageIds.selectManualVideoCover,
      idempotencyKey: context.idempotencyKey,
    ),
  );

  CloudOperationInvocationContext _uploadCommandContext(
    String clientPageId,
    ContentMediaUploadCommandContext upload,
  ) {
    return _commandContext(
      clientPageId,
      idempotencyKey: upload.idempotencyKey,
      cancellation: upload.cancellation,
    );
  }

  CloudOperationInvocationContext _commandContext(
    String clientPageId, {
    required String idempotencyKey,
    CloudOperationCancellationSignal? cancellation,
  }) {
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
      cancellation: cancellation,
    );
  }
}
