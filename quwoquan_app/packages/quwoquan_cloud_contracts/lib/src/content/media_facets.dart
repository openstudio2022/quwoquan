import 'media_contracts.dart';
import '../operation_cancellation.dart';

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
  Future<ContentMediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  );

  Future<ContentMediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  );

  Future<ContentMediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  );
}

abstract interface class ContentMediaUploadQuery {
  Future<ContentMediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  );
}

abstract interface class ContentMediaAssetQuery {
  Future<ContentMediaAssetSlice> getMediaAsset(GetContentMediaAssetQuery query);
}

abstract interface class ContentMediaCoverCommandWriter {
  Future<ContentMediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
  );

  Future<ContentMediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
  );
}

abstract interface class ContentMediaOriginalAccessWriter {
  Future<ContentMediaOriginalAccessGrant> requestOriginalAccess(
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
        ContentMediaCoverCommandWriter,
        ContentMediaOriginalAccessWriter {}
