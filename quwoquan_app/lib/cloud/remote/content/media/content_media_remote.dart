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
  ) => client.contentMediaUploadSessionInitMediaUpload(
    command,
    context: invocationContext(
      ContentRequestPageIds.initMediaUpload,
      command: true,
    ),
  );

  @override
  Future<ContentMediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
  ) => client.contentMediaUploadSessionCompleteMediaUpload(
    command,
    context: invocationContext(
      ContentRequestPageIds.completeMediaUpload,
      command: true,
    ),
  );

  @override
  Future<ContentMediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
  ) => client.contentMediaUploadSessionAbortMediaUpload(
    command,
    context: invocationContext(
      ContentRequestPageIds.abortMediaUpload,
      command: true,
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
  ) => client.contentMediaAssetSelectAutoVideoCover(
    command,
    context: invocationContext(
      ContentRequestPageIds.selectAutoVideoCover,
      command: true,
    ),
  );

  @override
  Future<ContentMediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
  ) => client.contentMediaAssetSelectManualVideoCover(
    command,
    context: invocationContext(
      ContentRequestPageIds.selectManualVideoCover,
      command: true,
    ),
  );

}
