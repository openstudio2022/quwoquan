import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Typed Media test double used only by canonical local-contract tests.
/// It records the same command values that the production generated client
/// receives and never exposes a path, operation ID or dynamic response.
final class RecordingContentMediaFacet implements ContentMediaFacet {
  RecordingContentMediaFacet({this.loseFirstCompleteResponse = false});

  final bool loseFirstCompleteResponse;
  final List<InitContentMediaUploadCommand> initCommands =
      <InitContentMediaUploadCommand>[];
  final List<String> completedSessions = <String>[];
  final List<String> abortedSessions = <String>[];
  final List<SelectManualContentMediaCoverCommand> selectedManualCovers =
      <SelectManualContentMediaCoverCommand>[];
  final List<String> selectedAutoCoverMediaIds = <String>[];
  final Map<String, InitContentMediaUploadCommand> _uploadBySession =
      <String, InitContentMediaUploadCommand>{};
  final Map<String, String> _assetBySession = <String, String>{};
  final Set<String> _lostCompleteResponses = <String>{};
  int _sequence = 0;

  @override
  Future<ContentMediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
  ) async {
    initCommands.add(command);
    final sessionId = 'session_${++_sequence}';
    _uploadBySession[sessionId] = command;
    return ContentMediaUploadSessionCommandResult(
      sessionId: sessionId,
      assetId: null,
      status: ContentMediaUploadStatus.pending,
      objectKey: 'uploads/$sessionId',
      uploadUrl: Uri.parse('https://upload.quwoquan.test/$sessionId'),
      cdnUrl: null,
      expiresAt: DateTime.utc(2030),
      replayed: false,
    );
  }

  @override
  Future<ContentMediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
  ) async {
    final upload = _uploadBySession[command.sessionId];
    if (upload == null) throw StateError('upload session not found');
    completedSessions.add(command.sessionId);
    final index = command.sessionId.split('_').last;
    final prefix = upload.mediaType == ContentMediaType.video
        ? 'video'
        : upload.mediaType == ContentMediaType.image
        ? 'image'
        : upload.mediaType.name;
    final extension = upload.mediaType == ContentMediaType.video
        ? 'mp4'
        : 'jpg';
    final assetId = '${prefix}_asset_$index';
    _assetBySession[command.sessionId] = assetId;
    if (loseFirstCompleteResponse &&
        _lostCompleteResponses.add(command.sessionId)) {
      throw StateError('simulated lost complete response');
    }
    return ContentMediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: assetId,
      status: ContentMediaUploadStatus.completed,
      objectKey: 'media/$assetId',
      uploadUrl: null,
      cdnUrl: Uri.parse('https://cdn.quwoquan.test/$assetId.$extension'),
      expiresAt: DateTime.utc(2030),
      replayed: false,
    );
  }

  @override
  Future<ContentMediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
  ) async {
    abortedSessions.add(command.sessionId);
    _assetBySession.remove(command.sessionId);
    return ContentMediaUploadSessionCommandResult(
      sessionId: command.sessionId,
      assetId: null,
      status: ContentMediaUploadStatus.aborted,
      objectKey: 'uploads/${command.sessionId}',
      uploadUrl: null,
      cdnUrl: null,
      expiresAt: DateTime.utc(2030),
      replayed: false,
    );
  }

  @override
  Future<ContentMediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
  ) async {
    selectedManualCovers.add(command);
    final coverAssetId = command.coverAssetId ?? command.mediaId;
    final url = Uri.parse('https://cdn.quwoquan.test/$coverAssetId.jpg');
    return ContentMediaCoverSelectionResult(
      mediaId: command.mediaId,
      coverStrategy: 'manual',
      manualCoverAssetId: command.coverAssetId,
      coverFrameTimeMs: command.coverFrameTimeMs,
      thumbnailUrl: url,
      coverUrl: url,
    );
  }

  @override
  Future<ContentMediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
  ) async {
    selectedAutoCoverMediaIds.add(command.mediaId);
    final url = Uri.parse(
      'https://cdn.quwoquan.test/${command.mediaId}_cover.jpg',
    );
    return ContentMediaCoverSelectionResult(
      mediaId: command.mediaId,
      coverStrategy: 'first_frame',
      manualCoverAssetId: null,
      coverFrameTimeMs: 0,
      thumbnailUrl: url,
      coverUrl: url,
    );
  }

  @override
  Future<ContentMediaAssetSlice> getMediaAsset(
    GetContentMediaAssetQuery query,
  ) => throw UnsupportedError('not used by this local-contract fixture');

  @override
  Future<ContentMediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) async {
    final upload = _uploadBySession[query.sessionId];
    if (upload == null) throw StateError('upload session not found');
    final assetId = _assetBySession[query.sessionId];
    return ContentMediaUploadSessionSlice(
      sessionId: query.sessionId,
      version: assetId == null ? 1 : 2,
      assetId: assetId,
      objectKey: 'uploads/${query.sessionId}',
      mediaType: upload.mediaType,
      contentType: upload.contentType,
      fileSize: upload.fileSize,
      status: assetId == null
          ? ContentMediaUploadStatus.pending
          : ContentMediaUploadStatus.completed,
      createdAt: DateTime.utc(2030),
      updatedAt: DateTime.utc(2030),
      expiresAt: DateTime.utc(2030, 1, 1, 0, 15),
    );
  }

  @override
  Future<ContentMediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => throw UnsupportedError('not used by this local-contract fixture');
}
