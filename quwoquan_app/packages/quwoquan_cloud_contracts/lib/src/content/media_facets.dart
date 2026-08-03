import '../operation_cancellation.dart';
import 'content_operation_contracts.g.dart';

/// Stable command identity for one durable media-upload session transition.
///
/// The caller persists a distinct key for init, complete, and abort before
/// issuing the corresponding command. This keeps retries and app restarts on
/// the same server-side idempotency receipt rather than opening a second
/// session for the same source bytes.
final class ContentMediaUploadCommandContext {
  const ContentMediaUploadCommandContext({
    required this.idempotencyKey,
    this.cancellation,
  });

  final String idempotencyKey;
  final CloudOperationCancellationSignal? cancellation;
}

abstract interface class ContentMediaUploadCommandWriter {
  Future<MediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  );

  Future<MediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  );

  Future<MediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  );
}

abstract interface class ContentMediaUploadQuery {
  Future<MediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  );
}

abstract interface class ContentMediaAssetQuery {
  Future<MediaAssetSlice> getMediaAsset(GetContentMediaAssetQuery query);
}

final class ContentMediaAssetCommandContext {
  const ContentMediaAssetCommandContext({required this.idempotencyKey});

  final String idempotencyKey;
}

abstract interface class ContentMediaAssetCommandWriter {
  Future<MediaAssetDiscardResult> discardMediaAsset(
    DiscardContentMediaAssetCommand command,
    ContentMediaAssetCommandContext context,
  );
}

abstract interface class ContentMediaCoverCommandWriter {
  Future<MediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  );

  Future<MediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  );
}

abstract interface class ContentMediaOriginalAccessWriter {
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  );
}

/// App media capability packet. It stays below the ten-method facet limit and
/// contains only typed object operations; upload bytes still travel directly
/// to the server-issued object-storage grant.
abstract interface class ContentMediaFacet
    implements
        ContentMediaUploadCommandWriter,
        ContentMediaUploadQuery,
        ContentMediaAssetQuery,
        ContentMediaAssetCommandWriter,
        ContentMediaCoverCommandWriter,
        ContentMediaOriginalAccessWriter {}
