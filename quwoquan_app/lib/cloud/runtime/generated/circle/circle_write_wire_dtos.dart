import 'circle_write_wire_writable_keys.g.dart';

/// CreateCircle 可写字段（[CircleWriteWireWritableKeys.createCircle]）+ 客户端扩展键（Mock 合并用）。
///
/// 扩展键示例：`sectionConfig`、`autoSyncChat`、`avatar` 等，云侧可忽略。
class CircleCreateWireDto {
  CircleCreateWireDto({
    this.name,
    this.description,
    this.coverUrl,
    this.category,
    this.subCategory,
    this.tags,
    this.visibility,
    this.joinPolicy,
    this.kind,
    this.displaySubjectType,
    this.followEnabled,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
    Map<String, dynamic>? extra,
  }) : extra = extra ?? const {};

  final String? name;
  final String? description;
  final String? coverUrl;
  final String? category;
  final String? subCategory;
  final List<String>? tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;

  /// 非 metadata 可写字段、或 UI 专用键，写入 Mock / 全量合并。
  final Map<String, dynamic> extra;

  static const Set<String> _writableKeys =
      CircleWriteWireWritableKeys.createCircle;

  Map<String, dynamic> toRequestMap() {
    final m = <String, dynamic>{};
    if (name != null) m['name'] = name;
    if (description != null) m['description'] = description;
    if (coverUrl != null) m['coverUrl'] = coverUrl;
    if (category != null) m['category'] = category;
    if (subCategory != null) m['subCategory'] = subCategory;
    if (tags != null) m['tags'] = tags;
    if (visibility != null) m['visibility'] = visibility;
    if (joinPolicy != null) m['joinPolicy'] = joinPolicy;
    if (kind != null) m['kind'] = kind;
    if (displaySubjectType != null) {
      m['displaySubjectType'] = displaySubjectType;
    }
    if (followEnabled != null) m['followEnabled'] = followEnabled;
    if (linkedHomepageId != null) m['linkedHomepageId'] = linkedHomepageId;
    if (linkedHomepageType != null) {
      m['linkedHomepageType'] = linkedHomepageType;
    }
    if (linkedHomepageTitle != null) {
      m['linkedHomepageTitle'] = linkedHomepageTitle;
    }
    return m;
  }

  /// Remote POST 体 + Mock `_normalizedCircle` 合并源。
  Map<String, dynamic> toMockMergeMap() => {...toRequestMap(), ...extra};

  factory CircleCreateWireDto.fromMap(Map<String, dynamic> raw) {
    final m = Map<String, dynamic>.from(raw);
    final extra = <String, dynamic>{};
    for (final e in m.entries) {
      if (_writableKeys.contains(e.key)) continue;
      if (e.key == 'categoryId') continue;
      extra[e.key] = e.value;
    }
    List<String>? tags;
    final t = m['tags'];
    if (t is List) {
      tags = t.map((e) => e.toString()).toList(growable: false);
    }
    return CircleCreateWireDto(
      name: m['name']?.toString(),
      description: m['description']?.toString(),
      coverUrl: (m['coverUrl'] ?? m['cover'])?.toString(),
      category: (m['category'] ?? m['categoryId'])?.toString(),
      subCategory: m['subCategory']?.toString(),
      tags: tags,
      visibility: m['visibility']?.toString(),
      joinPolicy: m['joinPolicy']?.toString(),
      kind: m['kind']?.toString(),
      displaySubjectType: m['displaySubjectType']?.toString(),
      followEnabled: m['followEnabled'] as bool?,
      linkedHomepageId: m['linkedHomepageId']?.toString(),
      linkedHomepageType: m['linkedHomepageType']?.toString(),
      linkedHomepageTitle: m['linkedHomepageTitle']?.toString(),
      extra: extra,
    );
  }
}

/// UpdateCircle PATCH 体（仅包含调用方显式传入的键）。
class CircleUpdateWireDto {
  CircleUpdateWireDto._(this._patch);

  final Map<String, dynamic> _patch;

  Map<String, dynamic> toMap() => Map<String, dynamic>.from(_patch);

  factory CircleUpdateWireDto.fromMap(Map<String, dynamic> m) =>
      CircleUpdateWireDto._(Map<String, dynamic>.from(m));
}

/// CreateCircleGroup 可写字段（[CircleWriteWireWritableKeys.createCircleGroup]）。
class CircleGroupCreateWireDto {
  CircleGroupCreateWireDto({
    this.parentGroupId,
    this.groupType,
    this.nodeType,
    this.name,
    this.description,
    this.visibility,
    this.joinPolicy,
    this.managerIds,
    this.storageEnabled,
    this.noticeEnabled,
    Map<String, dynamic>? extra,
  }) : extra = extra ?? const {};

  final String? parentGroupId;
  final String? groupType;
  final String? nodeType;
  final String? name;
  final String? description;
  final String? visibility;
  final String? joinPolicy;
  final List<String>? managerIds;
  final bool? storageEnabled;
  final bool? noticeEnabled;
  final Map<String, dynamic> extra;

  static const Set<String> _writableKeys =
      CircleWriteWireWritableKeys.createCircleGroup;

  Map<String, dynamic> toMap() {
    final m = <String, dynamic>{...extra};
    if (parentGroupId != null) m['parentGroupId'] = parentGroupId;
    if (groupType != null) m['groupType'] = groupType;
    if (nodeType != null) m['nodeType'] = nodeType;
    if (name != null) m['name'] = name;
    if (description != null) m['description'] = description;
    if (visibility != null) m['visibility'] = visibility;
    if (joinPolicy != null) m['joinPolicy'] = joinPolicy;
    if (managerIds != null) m['managerIds'] = managerIds;
    if (storageEnabled != null) m['storageEnabled'] = storageEnabled;
    if (noticeEnabled != null) m['noticeEnabled'] = noticeEnabled;
    return m;
  }

  factory CircleGroupCreateWireDto.fromMap(Map<String, dynamic> raw) {
    final m = Map<String, dynamic>.from(raw);
    final extra = <String, dynamic>{};
    for (final e in m.entries) {
      if (!_writableKeys.contains(e.key)) {
        extra[e.key] = e.value;
      }
    }
    List<String>? managers;
    final mm = m['managerIds'];
    if (mm is List) {
      managers = mm.map((e) => e.toString()).toList(growable: false);
    }
    return CircleGroupCreateWireDto(
      parentGroupId: m['parentGroupId']?.toString(),
      groupType: m['groupType']?.toString(),
      nodeType: m['nodeType']?.toString(),
      name: m['name']?.toString(),
      description: m['description']?.toString(),
      visibility: m['visibility']?.toString(),
      joinPolicy: m['joinPolicy']?.toString(),
      managerIds: managers,
      storageEnabled: m['storageEnabled'] as bool?,
      noticeEnabled: m['noticeEnabled'] as bool?,
      extra: extra,
    );
  }
}

/// UpdateCircleGroup PATCH 体。
class CircleGroupUpdateWireDto {
  CircleGroupUpdateWireDto._(this._patch);

  final Map<String, dynamic> _patch;

  Map<String, dynamic> toMap() => Map<String, dynamic>.from(_patch);

  factory CircleGroupUpdateWireDto.fromMap(Map<String, dynamic> m) =>
      CircleGroupUpdateWireDto._(Map<String, dynamic>.from(m));
}

/// CreateCircleFile 可写字段。
class CircleFileCreateWireDto {
  const CircleFileCreateWireDto({
    this.parentFolderId,
    required this.name,
    required this.fileType,
    this.mimeType,
    this.sizeBytes,
  });

  final String? parentFolderId;
  final String name;
  final String fileType;
  final String? mimeType;
  final int? sizeBytes;

  Map<String, dynamic> toMap() => {
        if (parentFolderId != null) 'parentFolderId': parentFolderId,
        'name': name,
        'fileType': fileType,
        if (mimeType != null) 'mimeType': mimeType,
        if (sizeBytes != null) 'sizeBytes': sizeBytes,
      };

  factory CircleFileCreateWireDto.fromMap(Map<String, dynamic> m) {
    return CircleFileCreateWireDto(
      parentFolderId: m['parentFolderId']?.toString(),
      name: (m['name'] ?? '').toString(),
      fileType: (m['fileType'] ?? 'file').toString(),
      mimeType: m['mimeType']?.toString(),
      sizeBytes: (m['sizeBytes'] as num?)?.toInt(),
    );
  }
}

/// UpdateCircleFile PATCH 体。
class CircleFileUpdateWireDto {
  const CircleFileUpdateWireDto({this.name, this.status});

  final String? name;
  final String? status;

  Map<String, dynamic> toMap() {
    final o = <String, dynamic>{};
    if (name != null) o['name'] = name;
    if (status != null) o['status'] = status;
    return o;
  }

  factory CircleFileUpdateWireDto.fromMap(Map<String, dynamic> m) {
    return CircleFileUpdateWireDto(
      name: m['name']?.toString(),
      status: m['status']?.toString(),
    );
  }
}

/// ReportCircleBehavior 请求体（fields.yaml `CircleBehaviorReport`）。
class CircleBehaviorReportWireDto {
  const CircleBehaviorReportWireDto({
    this.userId,
    this.circleId,
    this.eventType,
    this.sessionId,
    this.type,
    Map<String, dynamic>? extra,
  }) : extra = extra ?? const {};

  final String? userId;
  final String? circleId;

  /// 云契约主字段（与集成测试一致）。
  final String? eventType;

  /// 旧客户端可能使用 `type`。
  final String? type;
  final String? sessionId;
  final Map<String, dynamic> extra;

  Map<String, dynamic> toMap() => {
        if (userId != null) 'userId': userId,
        if (circleId != null) 'circleId': circleId,
        if (eventType != null) 'eventType': eventType,
        if (type != null) 'type': type,
        if (sessionId != null) 'sessionId': sessionId,
        ...extra,
      };

  factory CircleBehaviorReportWireDto.fromMap(Map<String, dynamic> m) {
    final copy = Map<String, dynamic>.from(m);
    return CircleBehaviorReportWireDto(
      userId: copy.remove('userId')?.toString(),
      circleId: copy.remove('circleId')?.toString(),
      eventType: copy.remove('eventType')?.toString(),
      type: copy.remove('type')?.toString(),
      sessionId: copy.remove('sessionId')?.toString(),
      extra: copy,
    );
  }
}
