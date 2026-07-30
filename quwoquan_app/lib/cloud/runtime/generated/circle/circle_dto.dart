import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_section_config_dto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CircleDisplaySubjectType,
        CircleJoinPolicy,
        CircleKind,
        CircleStatus,
        CircleVisibility;

/// 圈子聚合根 DTO。
///
/// 字段对齐：contracts/metadata/circle/circle/circle/fields.yaml Circle；
/// Dart/JSON 映射约定见 `quwoquan_service/contracts/metadata/circle/circle/circle/dart_type_mapping.yaml`。
class CircleDto {
  final String id;
  final String name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;

  /// 圈子独立头像（头部头像簇主体）；缺省由 UI 回退 coverUrl。
  final String? iconUrl;
  final String ownerId;
  final String? category;
  final List<String> tags;
  final int memberCount;
  final int postCount;
  final int weeklyActiveCount;
  final CircleStatus status;
  final CircleVisibility visibility;
  final CircleJoinPolicy joinPolicy;
  final CircleKind kind;
  final CircleDisplaySubjectType displaySubjectType;
  final bool followEnabled;
  final String? defaultPublicGroupId;
  final String? conversationId;
  final bool autoSyncChat;
  final List<CircleSectionConfigDto> sectionConfig;
  final int storageUsedBytes;
  final int storageQuotaBytes;
  final String? domainId;
  final String? subCategory;
  final DateTime createdAt;
  final DateTime updatedAt;

  const CircleDto({
    required this.id,
    required this.name,
    this.description,
    this.rulesText,
    this.welcomeMessage,
    this.coverUrl,
    this.iconUrl,
    required this.ownerId,
    this.category,
    this.tags = const [],
    this.memberCount = 0,
    this.postCount = 0,
    this.weeklyActiveCount = 0,
    this.status = CircleStatus.active,
    this.visibility = CircleVisibility.public,
    this.joinPolicy = CircleJoinPolicy.open,
    this.kind = CircleKind.interest,
    this.displaySubjectType = CircleDisplaySubjectType.circle,
    this.followEnabled = true,
    this.defaultPublicGroupId,
    this.conversationId,
    this.autoSyncChat = true,
    this.sectionConfig = const [],
    this.storageUsedBytes = 0,
    this.storageQuotaBytes = 1073741824,
    this.domainId,
    this.subCategory,
    required this.createdAt,
    required this.updatedAt,
  });

  factory CircleDto.fromMap(Map<String, dynamic> m) {
    return CircleDto(
      id: (m['id'] ?? '').toString(),
      name: (m['name'] ?? '').toString(),
      description: m['description'] as String?,
      rulesText: m['rulesText'] as String?,
      welcomeMessage: m['welcomeMessage'] as String?,
      coverUrl: m['coverUrl'] as String?,
      iconUrl: m['iconUrl'] as String?,
      ownerId: (m['ownerId'] ?? '').toString(),
      category: m['category'] as String?,
      tags:
          (m['tags'] as List<dynamic>?)?.map((e) => e.toString()).toList() ??
          const [],
      memberCount: (m['memberCount'] as num?)?.toInt() ?? 0,
      postCount: (m['postCount'] as num?)?.toInt() ?? 0,
      weeklyActiveCount: (m['weeklyActiveCount'] as num?)?.toInt() ?? 0,
      status: CircleStatus.fromWire(m['status'] ?? 'active'),
      visibility: CircleVisibility.fromWire(m['visibility'] ?? 'public'),
      joinPolicy: CircleJoinPolicy.fromWire(m['joinPolicy'] ?? 'open'),
      kind: CircleKind.fromWire(m['kind'] ?? 'interest'),
      displaySubjectType: CircleDisplaySubjectType.fromWire(
        m['displaySubjectType'] ?? 'circle',
      ),
      followEnabled: m['followEnabled'] as bool? ?? true,
      defaultPublicGroupId: m['defaultPublicGroupId']?.toString(),
      conversationId: m['conversationId'] as String?,
      autoSyncChat: m['autoSyncChat'] as bool? ?? true,
      sectionConfig:
          (m['sectionConfig'] as List<dynamic>?)
              ?.whereType<Map<String, dynamic>>()
              .map(CircleSectionConfigDto.fromMap)
              .toList() ??
          const [],
      storageUsedBytes: (m['storageUsedBytes'] as num?)?.toInt() ?? 0,
      storageQuotaBytes:
          (m['storageQuotaBytes'] as num?)?.toInt() ?? 1073741824,
      domainId: m['domainId'] as String?,
      subCategory: m['subCategory'] as String?,
      createdAt: _parseDateTime(m['createdAt']),
      updatedAt: _parseDateTime(m['updatedAt']),
    );
  }

  Map<String, dynamic> toMap() => {
    'id': id,
    'name': name,
    if (description != null) 'description': description,
    if (rulesText != null) 'rulesText': rulesText,
    if (welcomeMessage != null) 'welcomeMessage': welcomeMessage,
    if (coverUrl != null) 'coverUrl': coverUrl,
    if (iconUrl != null) 'iconUrl': iconUrl,
    'ownerId': ownerId,
    if (category != null) 'category': category,
    'tags': tags,
    'memberCount': memberCount,
    'postCount': postCount,
    'weeklyActiveCount': weeklyActiveCount,
    'status': status.wireValue,
    'visibility': visibility.wireValue,
    'joinPolicy': joinPolicy.wireValue,
    'kind': kind.wireValue,
    'displaySubjectType': displaySubjectType.wireValue,
    'followEnabled': followEnabled,
    if (defaultPublicGroupId != null)
      'defaultPublicGroupId': defaultPublicGroupId,
    if (conversationId != null) 'conversationId': conversationId,
    'autoSyncChat': autoSyncChat,
    'sectionConfig': sectionConfig.map((s) => s.toMap()).toList(),
    'storageUsedBytes': storageUsedBytes,
    'storageQuotaBytes': storageQuotaBytes,
    if (domainId != null) 'domainId': domainId,
    if (subCategory != null) 'subCategory': subCategory,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  static DateTime _parseDateTime(dynamic v) {
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }

  CircleDto copyWith({
    String? id,
    String? name,
    String? description,
    String? rulesText,
    String? welcomeMessage,
    String? coverUrl,
    String? iconUrl,
    String? ownerId,
    String? category,
    List<String>? tags,
    int? memberCount,
    int? postCount,
    int? weeklyActiveCount,
    CircleStatus? status,
    CircleVisibility? visibility,
    CircleJoinPolicy? joinPolicy,
    CircleKind? kind,
    CircleDisplaySubjectType? displaySubjectType,
    bool? followEnabled,
    String? defaultPublicGroupId,
    String? conversationId,
    bool? autoSyncChat,
    List<CircleSectionConfigDto>? sectionConfig,
    int? storageUsedBytes,
    int? storageQuotaBytes,
    String? domainId,
    String? subCategory,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return CircleDto(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      rulesText: rulesText ?? this.rulesText,
      welcomeMessage: welcomeMessage ?? this.welcomeMessage,
      coverUrl: coverUrl ?? this.coverUrl,
      iconUrl: iconUrl ?? this.iconUrl,
      ownerId: ownerId ?? this.ownerId,
      category: category ?? this.category,
      tags: tags ?? this.tags,
      memberCount: memberCount ?? this.memberCount,
      postCount: postCount ?? this.postCount,
      weeklyActiveCount: weeklyActiveCount ?? this.weeklyActiveCount,
      status: status ?? this.status,
      visibility: visibility ?? this.visibility,
      joinPolicy: joinPolicy ?? this.joinPolicy,
      kind: kind ?? this.kind,
      displaySubjectType: displaySubjectType ?? this.displaySubjectType,
      followEnabled: followEnabled ?? this.followEnabled,
      defaultPublicGroupId: defaultPublicGroupId ?? this.defaultPublicGroupId,
      conversationId: conversationId ?? this.conversationId,
      autoSyncChat: autoSyncChat ?? this.autoSyncChat,
      sectionConfig: sectionConfig ?? this.sectionConfig,
      storageUsedBytes: storageUsedBytes ?? this.storageUsedBytes,
      storageQuotaBytes: storageQuotaBytes ?? this.storageQuotaBytes,
      domainId: domainId ?? this.domainId,
      subCategory: subCategory ?? this.subCategory,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}
