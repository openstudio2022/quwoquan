import '../operation_request_payload.dart';

enum ContentMediaType { image, video, audio, file }

enum ContentMediaAccessPolicy { ownerOnly, referencedPost, public }

enum ContentMediaUploadStatus { pending, completed, aborted }

enum ContentMediaProcessingStatus { processing, ready, rejected, deleted }

enum ContentMediaOriginalAccessPurpose { view, save }

extension on ContentMediaAccessPolicy {
  String get wireName => switch (this) {
    ContentMediaAccessPolicy.ownerOnly => 'owner_only',
    ContentMediaAccessPolicy.referencedPost => 'referenced_post',
    ContentMediaAccessPolicy.public => 'public',
  };
}

final class InitContentMediaUploadCommand {
  InitContentMediaUploadCommand({
    required this.mediaType,
    required String contentType,
    required this.fileSize,
    required String expectedSha256,
  }) : contentType = _requiredText(contentType, 'contentType'),
       expectedSha256 = _normalizeSHA256(expectedSha256) {
    if (fileSize <= 0) {
      throw ArgumentError.value(fileSize, 'fileSize', 'must be > 0');
    }
  }

  final ContentMediaType mediaType;
  final String contentType;
  final int fileSize;
  final String expectedSha256;
}

final class CompleteContentMediaUploadCommand {
  CompleteContentMediaUploadCommand({
    required String sessionId,
    this.accessPolicy = ContentMediaAccessPolicy.ownerOnly,
  }) : sessionId = _requiredText(sessionId, 'sessionId');

  final String sessionId;
  final ContentMediaAccessPolicy accessPolicy;
}

final class AbortContentMediaUploadCommand {
  AbortContentMediaUploadCommand({required String sessionId})
    : sessionId = _requiredText(sessionId, 'sessionId');

  final String sessionId;
}

final class GetContentMediaUploadSessionQuery {
  GetContentMediaUploadSessionQuery({required String sessionId})
    : sessionId = _requiredText(sessionId, 'sessionId');

  final String sessionId;
}

final class GetContentMediaAssetQuery {
  GetContentMediaAssetQuery({required String mediaId})
    : mediaId = _requiredText(mediaId, 'mediaId');

  final String mediaId;
}

final class DiscardContentMediaAssetCommand {
  DiscardContentMediaAssetCommand({required String mediaId})
    : mediaId = _requiredText(mediaId, 'mediaId');

  final String mediaId;
}

final class RequestContentMediaOriginalAccessCommand {
  RequestContentMediaOriginalAccessCommand({
    required String mediaId,
    this.purpose = ContentMediaOriginalAccessPurpose.view,
  }) : mediaId = _requiredText(mediaId, 'mediaId');

  final String mediaId;
  final ContentMediaOriginalAccessPurpose purpose;
}

final class SelectAutoContentMediaCoverCommand {
  SelectAutoContentMediaCoverCommand({required String mediaId})
    : mediaId = _requiredText(mediaId, 'mediaId');

  final String mediaId;
}

final class SelectManualContentMediaCoverCommand {
  SelectManualContentMediaCoverCommand({
    required String mediaId,
    String? coverAssetId,
    this.coverFrameTimeMs = 0,
  }) : mediaId = _requiredText(mediaId, 'mediaId'),
       coverAssetId = _optionalText(coverAssetId) {
    if (this.coverAssetId == null && coverFrameTimeMs < 0) {
      throw ArgumentError.value(
        coverFrameTimeMs,
        'coverFrameTimeMs',
        'must be >= 0',
      );
    }
    if (this.coverAssetId != null && coverFrameTimeMs != 0) {
      throw ArgumentError(
        'coverAssetId and coverFrameTimeMs are mutually exclusive',
      );
    }
  }

  final String mediaId;
  final String? coverAssetId;
  final int coverFrameTimeMs;
}

final class ContentMediaUploadSessionCommandResult {
  const ContentMediaUploadSessionCommandResult({
    required this.sessionId,
    required this.assetId,
    required this.status,
    required this.uploadUrl,
    required this.expiresAt,
    required this.replayed,
  });

  final String sessionId;
  final String? assetId;
  final ContentMediaUploadStatus status;
  final Uri? uploadUrl;
  final DateTime expiresAt;
  final bool replayed;
}

final class ContentMediaUploadSessionSlice {
  const ContentMediaUploadSessionSlice({
    required this.sessionId,
    required this.version,
    required this.assetId,
    required this.mediaType,
    required this.contentType,
    required this.fileSize,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    required this.expiresAt,
  });

  final String sessionId;
  final int version;
  final String? assetId;
  final ContentMediaType mediaType;
  final String contentType;
  final int fileSize;
  final ContentMediaUploadStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime expiresAt;
}

final class ContentMediaAssetSlice {
  const ContentMediaAssetSlice({
    required this.assetId,
    required this.version,
    required this.mediaType,
    required this.contentType,
    required this.fileSize,
    required this.status,
    required this.accessPolicy,
    required this.cdnUrl,
    this.imageWidth,
    this.imageHeight,
    this.imageDeliveryContentType,
    this.imageDominantColor,
    this.imageLqip,
    this.imageContentProfile,
    this.imageDerivativePolicyVersion,
  });

  final String assetId;
  final int version;
  final ContentMediaType mediaType;
  final String contentType;
  final int fileSize;
  final ContentMediaProcessingStatus status;
  final ContentMediaAccessPolicy accessPolicy;
  final Uri cdnUrl;
  final int? imageWidth;
  final int? imageHeight;
  final String? imageDeliveryContentType;
  final String? imageDominantColor;
  final String? imageLqip;
  final String? imageContentProfile;
  final int? imageDerivativePolicyVersion;
}

final class ContentMediaAssetDiscardResult {
  const ContentMediaAssetDiscardResult({
    required this.mediaId,
    required this.status,
    required this.replayed,
  });

  final String mediaId;
  final ContentMediaProcessingStatus status;
  final bool replayed;
}

final class ContentMediaOriginalAccessGrant {
  const ContentMediaOriginalAccessGrant({
    required this.mediaId,
    required this.status,
    required this.originalUrl,
    required this.format,
    required this.sizeBytes,
    required this.expiresAt,
    required this.ttlSeconds,
    required this.auditId,
  });

  final String mediaId;
  final String status;
  final Uri originalUrl;
  final String format;
  final int sizeBytes;
  final DateTime expiresAt;
  final int ttlSeconds;
  final String auditId;
}

final class ContentMediaCoverSelectionResult {
  const ContentMediaCoverSelectionResult({
    required this.mediaId,
    required this.coverStrategy,
    required this.manualCoverAssetId,
    required this.coverFrameTimeMs,
    required this.thumbnailUrl,
    required this.coverUrl,
  });

  final String mediaId;
  final String coverStrategy;
  final String? manualCoverAssetId;
  final int coverFrameTimeMs;
  final Uri thumbnailUrl;
  final Uri coverUrl;
}

CloudOperationRequestPayload encodeInitContentMediaUploadCommand(
  InitContentMediaUploadCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'mediaType': command.mediaType.name,
    'contentType': command.contentType,
    'fileSize': command.fileSize,
    'expectedSha256': command.expectedSha256,
  },
);

CloudOperationRequestPayload encodeCompleteContentMediaUploadCommand(
  CompleteContentMediaUploadCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'sessionId': command.sessionId},
  body: <String, Object?>{'accessPolicy': command.accessPolicy.wireName},
);

CloudOperationRequestPayload encodeAbortContentMediaUploadCommand(
  AbortContentMediaUploadCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'sessionId': command.sessionId},
);

CloudOperationRequestPayload encodeGetContentMediaUploadSessionQuery(
  GetContentMediaUploadSessionQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'sessionId': query.sessionId},
);

CloudOperationRequestPayload encodeGetContentMediaAssetQuery(
  GetContentMediaAssetQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'mediaId': query.mediaId},
);

CloudOperationRequestPayload encodeDiscardContentMediaAssetCommand(
  DiscardContentMediaAssetCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'mediaId': command.mediaId},
);

CloudOperationRequestPayload encodeRequestContentMediaOriginalAccessCommand(
  RequestContentMediaOriginalAccessCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'mediaId': command.mediaId},
  body: <String, Object?>{'purpose': command.purpose.name},
);

CloudOperationRequestPayload encodeSelectAutoContentMediaCoverCommand(
  SelectAutoContentMediaCoverCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'mediaId': command.mediaId},
);

CloudOperationRequestPayload encodeSelectManualContentMediaCoverCommand(
  SelectManualContentMediaCoverCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'mediaId': command.mediaId},
  body: <String, Object?>{
    if (command.coverAssetId != null) 'coverAssetId': command.coverAssetId,
    'coverFrameTimeMs': command.coverFrameTimeMs,
  },
);

ContentMediaUploadSessionCommandResult
decodeContentMediaUploadSessionCommandResult(Object? value) {
  final map = _object(value, 'ContentMediaUploadSessionCommandResult');
  return ContentMediaUploadSessionCommandResult(
    sessionId: _string(map, 'sessionId'),
    assetId: _optionalString(map, 'assetId'),
    status: _uploadStatus(map, 'status'),
    uploadUrl: _optionalUri(map, 'uploadUrl'),
    expiresAt: _timestamp(map, 'expiresAt'),
    replayed: _boolean(map, 'replayed'),
  );
}

ContentMediaUploadSessionSlice decodeContentMediaUploadSessionSlice(
  Object? value,
) {
  final map = _object(value, 'ContentMediaUploadSessionSlice');
  return ContentMediaUploadSessionSlice(
    sessionId: _string(map, 'sessionId'),
    version: _positiveInteger(map, 'version'),
    assetId: _optionalString(map, 'assetId'),
    mediaType: _mediaType(map, 'mediaType'),
    contentType: _string(map, 'contentType'),
    fileSize: _positiveInteger(map, 'fileSize'),
    status: _uploadStatus(map, 'status'),
    createdAt: _timestamp(map, 'createdAt'),
    updatedAt: _timestamp(map, 'updatedAt'),
    expiresAt: _timestamp(map, 'expiresAt'),
  );
}

ContentMediaAssetSlice decodeContentMediaAssetSlice(Object? value) {
  final map = _object(value, 'ContentMediaAssetSlice');
  return ContentMediaAssetSlice(
    assetId: _string(map, 'assetId'),
    version: _positiveInteger(map, 'version'),
    mediaType: _mediaType(map, 'mediaType'),
    contentType: _string(map, 'contentType'),
    fileSize: _positiveInteger(map, 'fileSize'),
    status: _processingStatus(map, 'status'),
    accessPolicy: _accessPolicy(map, 'accessPolicy'),
    cdnUrl: _uri(map, 'cdnUrl'),
    imageWidth: _optionalPositiveInteger(map, 'imageWidth'),
    imageHeight: _optionalPositiveInteger(map, 'imageHeight'),
    imageDeliveryContentType: _optionalString(map, 'imageDeliveryContentType'),
    imageDominantColor: _optionalString(map, 'imageDominantColor'),
    imageLqip: _optionalString(map, 'imageLqip'),
    imageContentProfile: _optionalString(map, 'imageContentProfile'),
    imageDerivativePolicyVersion: _optionalPositiveInteger(
      map,
      'imageDerivativePolicyVersion',
    ),
  );
}

ContentMediaAssetDiscardResult decodeContentMediaAssetDiscardResult(
  Object? value,
) {
  final map = _object(value, 'ContentMediaAssetDiscardResult');
  final status = _processingStatus(map, 'status');
  if (status != ContentMediaProcessingStatus.deleted) {
    throw FormatException('status must be deleted, got ${status.name}');
  }
  return ContentMediaAssetDiscardResult(
    mediaId: _string(map, 'mediaId'),
    status: status,
    replayed: _boolean(map, 'replayed'),
  );
}

ContentMediaOriginalAccessGrant decodeContentMediaOriginalAccessGrant(
  Object? value,
) {
  final map = _object(value, 'ContentMediaOriginalAccessGrant');
  final status = _string(map, 'status');
  if (status != 'granted') {
    throw FormatException('status must be granted, got $status');
  }
  return ContentMediaOriginalAccessGrant(
    mediaId: _string(map, 'mediaId'),
    status: status,
    originalUrl: _uri(map, 'originalUrl'),
    format: _string(map, 'format'),
    sizeBytes: _positiveInteger(map, 'sizeBytes'),
    expiresAt: _timestamp(map, 'expiresAt'),
    ttlSeconds: _positiveInteger(map, 'ttlSeconds'),
    auditId: _string(map, 'auditId'),
  );
}

ContentMediaCoverSelectionResult decodeContentMediaCoverSelectionResult(
  Object? value,
) {
  final map = _object(value, 'ContentMediaCoverSelectionResult');
  return ContentMediaCoverSelectionResult(
    mediaId: _string(map, 'mediaId'),
    coverStrategy: _string(map, 'coverStrategy'),
    manualCoverAssetId: _optionalString(map, 'manualCoverAssetId'),
    coverFrameTimeMs: _nonNegativeInteger(map, 'coverFrameTimeMs'),
    thumbnailUrl: _uri(map, 'thumbnailUrl'),
    coverUrl: _uri(map, 'coverUrl'),
  );
}

Map<String, Object?> _object(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) throw FormatException('$key must be a string');
  return _optionalText(value);
}

int _integer(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int) throw FormatException('$key must be an integer');
  return value;
}

int _positiveInteger(Map<String, Object?> map, String key) {
  final value = _integer(map, key);
  if (value <= 0) throw FormatException('$key must be > 0');
  return value;
}

int? _optionalPositiveInteger(Map<String, Object?> map, String key) {
  if (!map.containsKey(key) || map[key] == null) {
    return null;
  }
  return _positiveInteger(map, key);
}

int _nonNegativeInteger(Map<String, Object?> map, String key) {
  final value = _integer(map, key);
  if (value < 0) throw FormatException('$key must be >= 0');
  return value;
}

bool _boolean(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

DateTime _timestamp(Map<String, Object?> map, String key) {
  final parsed = DateTime.tryParse(_string(map, key));
  if (parsed == null) throw FormatException('$key must be RFC3339');
  return parsed.toUtc();
}

Uri _uri(Map<String, Object?> map, String key) {
  final uri = Uri.tryParse(_string(map, key));
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    throw FormatException('$key must be an absolute URL');
  }
  return uri;
}

Uri? _optionalUri(Map<String, Object?> map, String key) {
  final value = _optionalString(map, key);
  if (value == null) return null;
  final uri = Uri.tryParse(value);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    throw FormatException('$key must be an absolute URL');
  }
  return uri;
}

ContentMediaType _mediaType(Map<String, Object?> map, String key) =>
    _enumValue(ContentMediaType.values, _string(map, key), key);

ContentMediaUploadStatus _uploadStatus(Map<String, Object?> map, String key) =>
    _enumValue(ContentMediaUploadStatus.values, _string(map, key), key);

ContentMediaProcessingStatus _processingStatus(
  Map<String, Object?> map,
  String key,
) => _enumValue(ContentMediaProcessingStatus.values, _string(map, key), key);

ContentMediaAccessPolicy _accessPolicy(Map<String, Object?> map, String key) {
  final raw = _string(map, key);
  return switch (raw) {
    'owner_only' => ContentMediaAccessPolicy.ownerOnly,
    'referenced_post' => ContentMediaAccessPolicy.referencedPost,
    'public' => ContentMediaAccessPolicy.public,
    _ => throw FormatException('$key has unsupported value $raw'),
  };
}

T _enumValue<T extends Enum>(List<T> values, String raw, String key) {
  for (final value in values) {
    if (value.name == raw) return value;
  }
  throw FormatException('$key has unsupported value $raw');
}

String _normalizeSHA256(String value) {
  final normalized = value.trim().toLowerCase();
  final raw = normalized.startsWith('sha256:')
      ? normalized.substring('sha256:'.length)
      : normalized;
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(raw)) {
    throw ArgumentError.value(value, 'expectedSha256', 'must be SHA-256');
  }
  return 'sha256:$raw';
}

String _requiredText(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return normalized;
}

String? _optionalText(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
