import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef MediaUploadSessionInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// MediaUploadSession 对象拥有的 generated client adapter。
final class RemoteContentMediaUploadSessionAdapter
    implements ContentMediaUploadCommandWriter, ContentMediaUploadQuery {
  const RemoteContentMediaUploadSessionAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final MediaUploadSessionInvocationContextFactory invocationContext;

  @override
  Future<MediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => client.contentMediaUploadSessionInitMediaUpload(
    command,
    context: _commandContext(ContentRequestPageIds.initMediaUpload, context),
  );

  @override
  Future<MediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => client.contentMediaUploadSessionCompleteMediaUpload(
    command,
    context: _commandContext(
      ContentRequestPageIds.completeMediaUpload,
      context,
    ),
  );

  @override
  Future<MediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => client.contentMediaUploadSessionAbortMediaUpload(
    command,
    context: _commandContext(ContentRequestPageIds.abortMediaUpload, context),
  );

  @override
  Future<MediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) => client.contentMediaUploadSessionGetMediaUploadSession(
    query,
    context: invocationContext(
      ContentRequestPageIds.getMediaUploadSession,
      command: false,
    ),
  );

  CloudOperationInvocationContext _commandContext(
    String clientPageId,
    ContentMediaUploadCommandContext upload,
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
      idempotencyKey: upload.idempotencyKey,
      deadlineAt: base.deadlineAt,
      cancellation: upload.cancellation,
    );
  }
}
