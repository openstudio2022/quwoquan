/// 圈子存储空间文件/文件夹 DTO。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml CircleFile
class CircleFileDto {
  final String id;
  final String circleId;
  final String? parentFolderId;
  final String name;
  final String fileType;
  final String? mimeType;
  final int sizeBytes;
  final String uploaderId;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;

  const CircleFileDto({
    required this.id,
    required this.circleId,
    this.parentFolderId,
    required this.name,
    required this.fileType,
    this.mimeType,
    this.sizeBytes = 0,
    required this.uploaderId,
    this.status = 'active',
    required this.createdAt,
    required this.updatedAt,
  });

  factory CircleFileDto.fromMap(Map<String, dynamic> m) {
    return CircleFileDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      circleId: (m['circleId'] ?? '').toString(),
      parentFolderId: m['parentFolderId'] as String?,
      name: (m['name'] ?? '').toString(),
      fileType: (m['fileType'] ?? 'file').toString(),
      mimeType: m['mimeType'] as String?,
      sizeBytes: (m['sizeBytes'] as num?)?.toInt() ?? 0,
      uploaderId: (m['uploaderId'] ?? '').toString(),
      status: (m['status'] ?? 'active').toString(),
      createdAt: _parseDateTime(m['createdAt']),
      updatedAt: _parseDateTime(m['updatedAt']),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'circleId': circleId,
        if (parentFolderId != null) 'parentFolderId': parentFolderId,
        'name': name,
        'fileType': fileType,
        if (mimeType != null) 'mimeType': mimeType,
        'sizeBytes': sizeBytes,
        'uploaderId': uploaderId,
        'status': status,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };

  bool get isFolder => fileType == 'folder';

  static DateTime _parseDateTime(dynamic v) {
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }
}
