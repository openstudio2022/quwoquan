import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only deterministic Media fixture. Production has no dependency on
/// this package; alpha runner supplies it explicitly through provider override.
final class AlphaContentMediaFacet implements ContentMediaFacet {
  AlphaContentMediaFacet({this.completedAssetStatus = MediaAssetStatus.ready});

  final Map<String, _AlphaUpload> _uploads = <String, _AlphaUpload>{};
  final Map<String, MediaAssetSlice> _assets = <String, MediaAssetSlice>{};
  final Map<String, MediaUploadSessionCommandResult> _initReceipts =
      <String, MediaUploadSessionCommandResult>{};
  final Map<String, MediaUploadSessionCommandResult> _completeReceipts =
      <String, MediaUploadSessionCommandResult>{};
  final Set<String> _discardedAssetIds = <String>{};
  final MediaAssetStatus completedAssetStatus;
  int _sequence = 0;

  @override
  Future<MediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final key = context.idempotencyKey.trim();
    final replay = _initReceipts[key];
    if (replay != null) {
      return _replayed(replay);
    }
    final id = 'alpha_media_upload_${++_sequence}';
    final expiresAt = DateTime.utc(2030, 1, 1, 0, 15);
    _uploads[id] = _AlphaUpload(command, expiresAt);
    final result = MediaUploadSessionCommandResult(
      sessionId: id,
      assetId: null,
      status: MediaUploadSessionStatus.pending,
      uploadUrl: Uri.parse('https://upload.alpha.example.invalid/$id'),
      expiresAt: expiresAt,
      replayed: false,
    );
    _initReceipts[key] = result;
    return result;
  }

  @override
  Future<MediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final key = context.idempotencyKey.trim();
    final replay = _completeReceipts[key];
    if (replay != null) {
      if (replay.sessionId != command.sessionId) {
        throw StateError('alpha media complete idempotency key mismatch');
      }
      return _replayed(replay);
    }
    final upload = _uploads[command.sessionId];
    if (upload == null) {
      throw StateError('alpha media upload session not found');
    }
    final assetId = 'alpha_media_asset_${command.sessionId}';
    final cdnUrl = Uri.parse('https://alpha-cdn.invalid/$assetId');
    upload
      ..assetId = assetId
      ..status = MediaUploadSessionStatus.completed;
    _assets[assetId] = MediaAssetSlice(
      assetId: assetId,
      version: 1,
      mediaType: upload.command.mediaType,
      mimeType: upload.command.mimeType,
      fileSize: upload.command.fileSize,
      status: completedAssetStatus,
      accessPolicy: command.accessPolicy,
      cdnUrl: cdnUrl,
    );
    final result = MediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: assetId,
      status: MediaUploadSessionStatus.completed,
      uploadUrl: null,
      expiresAt: upload.expiresAt,
      replayed: false,
      assetProcessingStatus: completedAssetStatus,
    );
    _completeReceipts[key] = result;
    return result;
  }

  @override
  Future<MediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final upload = _uploads.remove(command.sessionId);
    if (upload == null) {
      throw StateError('alpha media upload session not found');
    }
    return MediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: null,
      status: MediaUploadSessionStatus.aborted,
      uploadUrl: null,
      expiresAt: upload.expiresAt,
      replayed: false,
    );
  }

  @override
  Future<MediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) async {
    final upload = _uploads[query.sessionId];
    if (upload == null) {
      throw StateError('alpha media upload session not found');
    }
    return MediaUploadSessionSlice(
      sessionId: query.sessionId,
      version: upload.status == MediaUploadSessionStatus.completed ? 2 : 1,
      assetId: upload.assetId,
      mediaType: upload.command.mediaType,
      mimeType: upload.command.mimeType,
      fileSize: upload.command.fileSize,
      status: upload.status,
      createdAt: DateTime.utc(2030),
      updatedAt: DateTime.utc(2030),
      expiresAt: upload.expiresAt,
    );
  }

  @override
  Future<MediaAssetSlice> getMediaAsset(GetContentMediaAssetQuery query) async {
    final asset = _assets[query.mediaId];
    if (asset == null) throw StateError('alpha media asset not found');
    return asset;
  }

  @override
  Future<MediaAssetDiscardResult> discardMediaAsset(
    DiscardContentMediaAssetCommand command,
    ContentMediaAssetCommandContext context,
  ) async {
    if (_discardedAssetIds.contains(command.mediaId)) {
      return MediaAssetDiscardResult(
        mediaId: command.mediaId,
        status: MediaAssetDiscardStatus.deleted,
        replayed: true,
      );
    }
    if (_assets.remove(command.mediaId) == null) {
      throw StateError('alpha media asset not found');
    }
    _discardedAssetIds.add(command.mediaId);
    return MediaAssetDiscardResult(
      mediaId: command.mediaId,
      status: MediaAssetDiscardStatus.deleted,
      replayed: false,
    );
  }

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) async {
    final asset = await getMediaAsset(
      GetContentMediaAssetQuery(mediaId: command.mediaId),
    );
    return MediaOriginalAccessGrant(
      mediaId: asset.assetId,
      status: 'granted',
      originalUrl: asset.cdnUrl,
      format: asset.mimeType,
      sizeBytes: asset.fileSize,
      expiresAt: DateTime.utc(2030, 1, 1, 0, 5),
      ttlSeconds: 300,
      auditId: 'alpha_audit_${asset.assetId}',
    );
  }

  @override
  Future<MediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) async => _cover(command.mediaId, MediaCoverStrategy.firstFrame);

  @override
  Future<MediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) async =>
      _cover(command.mediaId, MediaCoverStrategy.manual, command.coverAssetId);

  MediaCoverSelectionResult _cover(
    String mediaId,
    MediaCoverStrategy strategy, [
    String? manualAssetId,
  ]) {
    final url = Uri.parse('https://alpha-cdn.invalid/$mediaId/cover');
    return MediaCoverSelectionResult(
      mediaId: mediaId,
      coverStrategy: strategy,
      manualCoverAssetId: manualAssetId,
      coverFrameTimeMs: 0,
      thumbnailUrl: url,
      coverUrl: url,
    );
  }
}

MediaUploadSessionCommandResult _replayed(
  MediaUploadSessionCommandResult result,
) {
  return MediaUploadSessionCommandResult(
    sessionId: result.sessionId,
    assetId: result.assetId,
    status: result.status,
    uploadUrl: result.uploadUrl,
    expiresAt: result.expiresAt,
    replayed: true,
    assetProcessingStatus: result.assetProcessingStatus,
  );
}

final class _AlphaUpload {
  _AlphaUpload(this.command, this.expiresAt);

  final InitContentMediaUploadCommand command;
  final DateTime expiresAt;
  String? assetId;
  MediaUploadSessionStatus status = MediaUploadSessionStatus.pending;
}
