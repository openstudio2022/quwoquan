import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Runtime transport-boundary Media typed double for local-contract tests.
/// It records the same command values that the production generated client
/// receives and never exposes a path, operation ID or dynamic response.
final class RecordingContentMediaFacet implements ContentMediaFacet {
  RecordingContentMediaFacet({
    this.loseFirstCompleteResponse = false,
    this.loseFirstDiscardResponse = false,
    this.failUploadSessionRead = false,
    this.failCompleteWithoutCommit = false,
    this.uploadExpirations = const <DateTime>[],
    this.completedAssetStatus = MediaAssetStatus.ready,
    this.completedAssetAccessPolicy = MediaAssetAccessPolicy.ownerOnly,
  });

  final bool loseFirstCompleteResponse;
  final bool loseFirstDiscardResponse;
  final bool failUploadSessionRead;
  final bool failCompleteWithoutCommit;
  final List<DateTime> uploadExpirations;
  final MediaAssetStatus completedAssetStatus;
  final MediaAssetAccessPolicy completedAssetAccessPolicy;
  final List<InitContentMediaUploadCommand> initCommands =
      <InitContentMediaUploadCommand>[];
  final List<String> initIdempotencyKeys = <String>[];
  final List<String> completeIdempotencyKeys = <String>[];
  final List<CompleteContentMediaUploadCommand> completeCommands =
      <CompleteContentMediaUploadCommand>[];
  final List<String> abortIdempotencyKeys = <String>[];
  final List<String> discardIdempotencyKeys = <String>[];
  final List<String> completedSessions = <String>[];
  final List<String> abortedSessions = <String>[];
  final List<SelectManualContentMediaCoverCommand> selectedManualCovers =
      <SelectManualContentMediaCoverCommand>[];
  final List<String> selectedAutoCoverMediaIds = <String>[];
  final List<String> coverIdempotencyKeys = <String>[];
  final List<DiscardContentMediaAssetCommand> discardCommands =
      <DiscardContentMediaAssetCommand>[];
  final Map<String, InitContentMediaUploadCommand> _uploadBySession =
      <String, InitContentMediaUploadCommand>{};
  final Map<String, String> _assetBySession = <String, String>{};
  final Map<String, String> _sessionByInitIdempotencyKey = <String, String>{};
  final Map<String, DateTime> _expiresAtBySession = <String, DateTime>{};
  final Set<String> _abortedSessions = <String>{};
  final Set<String> _lostCompleteResponses = <String>{};
  final Set<String> _lostDiscardResponses = <String>{};
  final Set<String> _discardedAssets = <String>{};
  int _sequence = 0;

  @override
  Future<MediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    final existingSessionId =
        _sessionByInitIdempotencyKey[context.idempotencyKey];
    if (existingSessionId != null) {
      final assetId = _assetBySession[existingSessionId];
      return MediaUploadSessionCommandResult(
        sessionId: existingSessionId,
        assetId: assetId,
        status: assetId == null
            ? MediaUploadSessionStatus.pending
            : MediaUploadSessionStatus.completed,
        uploadUrl: assetId == null
            ? Uri.parse('https://upload.quwoquan.test/$existingSessionId')
            : null,
        expiresAt: _expiresAtBySession[existingSessionId]!,
        replayed: true,
        assetProcessingStatus: assetId == null ? null : completedAssetStatus,
      );
    }
    initCommands.add(command);
    initIdempotencyKeys.add(context.idempotencyKey);
    final sessionId = 'session_${++_sequence}';
    final expiresAt = uploadExpirations.length >= _sequence
        ? uploadExpirations[_sequence - 1].toUtc()
        : DateTime.utc(2030);
    _sessionByInitIdempotencyKey[context.idempotencyKey] = sessionId;
    _uploadBySession[sessionId] = command;
    _expiresAtBySession[sessionId] = expiresAt;
    return MediaUploadSessionCommandResult(
      sessionId: sessionId,
      assetId: null,
      status: MediaUploadSessionStatus.pending,
      uploadUrl: Uri.parse('https://upload.quwoquan.test/$sessionId'),
      expiresAt: expiresAt,
      replayed: false,
    );
  }

  @override
  Future<MediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    completeIdempotencyKeys.add(context.idempotencyKey);
    completeCommands.add(command);
    final upload = _uploadBySession[command.sessionId];
    if (upload == null) throw StateError('upload session not found');
    completedSessions.add(command.sessionId);
    if (failCompleteWithoutCommit) {
      throw StateError('simulated pending complete failure');
    }
    final index = command.sessionId.split('_').last;
    final prefix = upload.mediaType == MediaType.video
        ? 'video'
        : upload.mediaType == MediaType.image
        ? 'image'
        : upload.mediaType.name;
    final assetId = '${prefix}_asset_$index';
    _assetBySession[command.sessionId] = assetId;
    if (loseFirstCompleteResponse &&
        _lostCompleteResponses.add(command.sessionId)) {
      throw StateError('simulated lost complete response');
    }
    return MediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: assetId,
      status: MediaUploadSessionStatus.completed,
      uploadUrl: null,
      expiresAt: _expiresAtBySession[command.sessionId]!,
      replayed: false,
      assetProcessingStatus: completedAssetStatus,
    );
  }

  @override
  Future<MediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) async {
    abortIdempotencyKeys.add(context.idempotencyKey);
    abortedSessions.add(command.sessionId);
    final completedAssetId = _assetBySession[command.sessionId];
    if (completedAssetId != null) {
      return MediaUploadSessionCommandResult(
        sessionId: command.sessionId,
        assetId: completedAssetId,
        status: MediaUploadSessionStatus.completed,
        uploadUrl: null,
        expiresAt: _expiresAtBySession[command.sessionId]!,
        replayed: true,
      );
    }
    _assetBySession.remove(command.sessionId);
    _abortedSessions.add(command.sessionId);
    return MediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: null,
      status: MediaUploadSessionStatus.aborted,
      uploadUrl: null,
      expiresAt: _expiresAtBySession[command.sessionId]!,
      replayed: false,
    );
  }

  @override
  Future<MediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) async {
    coverIdempotencyKeys.add(context.idempotencyKey);
    selectedManualCovers.add(command);
    final coverAssetId = command.coverAssetId ?? command.mediaId;
    final url = Uri.parse('https://cdn.quwoquan.test/$coverAssetId.jpg');
    return MediaCoverSelectionResult(
      mediaId: command.mediaId,
      coverStrategy: MediaCoverStrategy.manual,
      manualCoverAssetId: command.coverAssetId,
      coverFrameTimeMs: command.coverFrameTimeMs,
      thumbnailUrl: url,
      coverUrl: url,
    );
  }

  @override
  Future<MediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) async {
    coverIdempotencyKeys.add(context.idempotencyKey);
    selectedAutoCoverMediaIds.add(command.mediaId);
    final url = Uri.parse(
      'https://cdn.quwoquan.test/${command.mediaId}_cover.jpg',
    );
    return MediaCoverSelectionResult(
      mediaId: command.mediaId,
      coverStrategy: MediaCoverStrategy.firstFrame,
      manualCoverAssetId: null,
      coverFrameTimeMs: 0,
      thumbnailUrl: url,
      coverUrl: url,
    );
  }

  @override
  Future<MediaAssetSlice> getMediaAsset(GetContentMediaAssetQuery query) async {
    String? session;
    for (final entry in _assetBySession.entries) {
      if (entry.value == query.mediaId) {
        session = entry.key;
        break;
      }
    }
    if (session == null) {
      throw StateError('media asset not found');
    }
    final upload = _uploadBySession[session]!;
    return MediaAssetSlice(
      assetId: query.mediaId,
      version: 1,
      mediaType: upload.mediaType,
      mimeType: upload.mimeType,
      fileSize: upload.fileSize,
      status: completedAssetStatus,
      accessPolicy: completedAssetAccessPolicy,
      cdnUrl: Uri.parse(
        'https://cdn.quwoquan.test/media/image/s/asset/'
        '${query.mediaId}/v1/source.jpg',
      ),
    );
  }

  @override
  Future<MediaAssetDiscardResult> discardMediaAsset(
    DiscardContentMediaAssetCommand command,
    ContentMediaAssetCommandContext context,
  ) async {
    discardIdempotencyKeys.add(context.idempotencyKey);
    discardCommands.add(command);
    final replayed = !_discardedAssets.add(command.mediaId);
    if (loseFirstDiscardResponse &&
        _lostDiscardResponses.add(command.mediaId)) {
      throw StateError('simulated lost discard response');
    }
    return MediaAssetDiscardResult(
      mediaId: command.mediaId,
      status: MediaAssetDiscardStatus.deleted,
      replayed: replayed,
    );
  }

  @override
  Future<MediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) async {
    if (failUploadSessionRead) {
      throw StateError('simulated upload-session reconciliation failure');
    }
    final upload = _uploadBySession[query.sessionId];
    if (upload == null) throw StateError('upload session not found');
    final assetId = _assetBySession[query.sessionId];
    return MediaUploadSessionSlice(
      sessionId: query.sessionId,
      version: assetId == null ? 1 : 2,
      assetId: assetId,
      mediaType: upload.mediaType,
      mimeType: upload.mimeType,
      fileSize: upload.fileSize,
      status: _abortedSessions.contains(query.sessionId)
          ? MediaUploadSessionStatus.aborted
          : assetId == null
          ? MediaUploadSessionStatus.pending
          : MediaUploadSessionStatus.completed,
      createdAt: DateTime.utc(2030),
      updatedAt: DateTime.utc(2030),
      expiresAt: _expiresAtBySession[query.sessionId]!,
    );
  }

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => throw UnsupportedError('not used by this local-contract fixture');
}
