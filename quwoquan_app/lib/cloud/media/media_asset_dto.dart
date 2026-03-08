/// Typed DTO for media assets, aligned with Go runtime/media.MediaAsset.
class MediaAssetDto {
  final String assetId;
  final String sessionId;
  final String category;
  final String ownerId;
  final String fileName;
  final String contentType;
  final int fileSize;
  final String ossKey;
  final String cdnUrl;
  final int? durationMs;
  final int? width;
  final int? height;
  final Map<String, dynamic>? metadata;
  final DateTime createdAt;

  const MediaAssetDto({
    required this.assetId,
    required this.sessionId,
    required this.category,
    required this.ownerId,
    required this.fileName,
    required this.contentType,
    required this.fileSize,
    required this.ossKey,
    required this.cdnUrl,
    this.durationMs,
    this.width,
    this.height,
    this.metadata,
    required this.createdAt,
  });

  factory MediaAssetDto.fromMap(Map<String, dynamic> map) {
    return MediaAssetDto(
      assetId: (map['assetId'] ?? '') as String,
      sessionId: (map['sessionId'] ?? '') as String,
      category: (map['category'] ?? '') as String,
      ownerId: (map['ownerId'] ?? '') as String,
      fileName: (map['fileName'] ?? '') as String,
      contentType: (map['contentType'] ?? '') as String,
      fileSize: (map['fileSize'] as num?)?.toInt() ?? 0,
      ossKey: (map['ossKey'] ?? '') as String,
      cdnUrl: (map['cdnUrl'] ?? '') as String,
      durationMs: (map['durationMs'] as num?)?.toInt(),
      width: (map['width'] as num?)?.toInt(),
      height: (map['height'] as num?)?.toInt(),
      metadata: map['metadata'] is Map
          ? (map['metadata'] as Map).cast<String, dynamic>()
          : null,
      createdAt:
          DateTime.tryParse((map['createdAt'] ?? '') as String) ??
              DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() => {
        'assetId': assetId,
        'sessionId': sessionId,
        'category': category,
        'ownerId': ownerId,
        'fileName': fileName,
        'contentType': contentType,
        'fileSize': fileSize,
        'ossKey': ossKey,
        'cdnUrl': cdnUrl,
        if (durationMs != null) 'durationMs': durationMs,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
        if (metadata != null) 'metadata': metadata,
        'createdAt': createdAt.toIso8601String(),
      };
}
