import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only deterministic Media fixture. Production has no dependency on
/// this package; alpha runner supplies it explicitly through provider override.
final class AlphaContentMediaFacet implements ContentMediaFacet {
  final Map<String, _AlphaUpload> _uploads = <String, _AlphaUpload>{};
  final Map<String, ContentMediaAssetSlice> _assets =
      <String, ContentMediaAssetSlice>{};
  int _sequence = 0;

  @override
  Future<ContentMediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final id = 'alpha_media_upload_${++_sequence}';
    final expiresAt = DateTime.utc(2030, 1, 1, 0, 15);
    _uploads[id] = _AlphaUpload(command, expiresAt);
    return ContentMediaUploadSessionCommandResult(
      sessionId: id,
      assetId: null,
      status: ContentMediaUploadStatus.pending,
      objectKey: 'alpha/uploads/$id',
      uploadUrl: Uri.parse('https://alpha-upload.invalid/$id'),
      cdnUrl: null,
      expiresAt: expiresAt,
      replayed: false,
    );
  }

  @override
  Future<ContentMediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final upload = _uploads[command.sessionId];
    if (upload == null)
      throw StateError('alpha media upload session not found');
    final assetId = 'alpha_media_asset_${command.sessionId}';
    final cdnUrl = Uri.parse('https://alpha-cdn.invalid/$assetId');
    upload
      ..assetId = assetId
      ..status = ContentMediaUploadStatus.completed;
    _assets[assetId] = ContentMediaAssetSlice(
      assetId: assetId,
      version: 1,
      mediaType: upload.command.mediaType,
      contentType: upload.command.contentType,
      fileSize: upload.command.fileSize,
      status: ContentMediaProcessingStatus.ready,
      accessPolicy: command.accessPolicy,
      cdnUrl: cdnUrl,
    );
    return ContentMediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: assetId,
      status: ContentMediaUploadStatus.completed,
      objectKey: 'alpha/media/$assetId',
      uploadUrl: null,
      cdnUrl: cdnUrl,
      expiresAt: upload.expiresAt,
      replayed: false,
    );
  }

  @override
  Future<ContentMediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final upload = _uploads.remove(command.sessionId);
    if (upload == null)
      throw StateError('alpha media upload session not found');
    return ContentMediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: null,
      status: ContentMediaUploadStatus.aborted,
      objectKey: 'alpha/uploads/${command.sessionId}',
      uploadUrl: null,
      cdnUrl: null,
      expiresAt: upload.expiresAt,
      replayed: false,
    );
  }

  @override
  Future<ContentMediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) async {
    final upload = _uploads[query.sessionId];
    if (upload == null)
      throw StateError('alpha media upload session not found');
    return ContentMediaUploadSessionSlice(
      sessionId: query.sessionId,
      version: upload.status == ContentMediaUploadStatus.completed ? 2 : 1,
      assetId: upload.assetId,
      objectKey: 'alpha/uploads/${query.sessionId}',
      mediaType: upload.command.mediaType,
      contentType: upload.command.contentType,
      fileSize: upload.command.fileSize,
      status: upload.status,
      createdAt: DateTime.utc(2030),
      updatedAt: DateTime.utc(2030),
      expiresAt: upload.expiresAt,
    );
  }

  @override
  Future<ContentMediaAssetSlice> getMediaAsset(
    GetContentMediaAssetQuery query,
  ) async {
    final asset = _assets[query.mediaId];
    if (asset == null) throw StateError('alpha media asset not found');
    return asset;
  }

  @override
  Future<ContentMediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) async {
    final asset = await getMediaAsset(
      GetContentMediaAssetQuery(mediaId: command.mediaId),
    );
    return ContentMediaOriginalAccessGrant(
      mediaId: asset.assetId,
      status: 'granted',
      originalUrl: asset.cdnUrl,
      format: asset.contentType,
      sizeBytes: asset.fileSize,
      expiresAt: DateTime.utc(2030, 1, 1, 0, 5),
      ttlSeconds: 300,
      auditId: 'alpha_audit_${asset.assetId}',
    );
  }

  @override
  Future<ContentMediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
  ) async => _cover(command.mediaId, 'first_frame');

  @override
  Future<ContentMediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
  ) async => _cover(command.mediaId, 'manual', command.coverAssetId);

  ContentMediaCoverSelectionResult _cover(
    String mediaId,
    String strategy, [
    String? manualAssetId,
  ]) {
    final url = Uri.parse('https://alpha-cdn.invalid/$mediaId/cover');
    return ContentMediaCoverSelectionResult(
      mediaId: mediaId,
      coverStrategy: strategy,
      manualCoverAssetId: manualAssetId,
      coverFrameTimeMs: 0,
      thumbnailUrl: url,
      coverUrl: url,
    );
  }
}

final class _AlphaUpload {
  _AlphaUpload(this.command, this.expiresAt);

  final InitContentMediaUploadCommand command;
  final DateTime expiresAt;
  String? assetId;
  ContentMediaUploadStatus status = ContentMediaUploadStatus.pending;
}
