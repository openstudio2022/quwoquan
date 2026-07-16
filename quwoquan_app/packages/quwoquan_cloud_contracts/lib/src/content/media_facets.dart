import 'media_contracts.dart';

abstract interface class ContentMediaUploadCommandWriter {
  Future<ContentMediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
  );

  Future<ContentMediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
  );

  Future<ContentMediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
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

abstract interface class ContentPostMediaBindingWriter {
  Future<BindContentPostMediaAssetsResult> bindPostMediaAssets(
    BindContentPostMediaAssetsCommand command,
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
        ContentMediaOriginalAccessWriter,
        ContentPostMediaBindingWriter {}
