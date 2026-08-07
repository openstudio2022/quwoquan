import 'package:quwoquan_app/service/content_service/content/post/application/public/assistant_use_policy_codec.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';
import 'package:quwoquan_cloud_contracts/generated/integration_contracts.dart'
    show LocationPoi;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy;

/// 通用发布设置状态模型（design B1），承载位置/公开/圈子选择，供创作、编辑等多页面复用。
class PublishSettings {
  const PublishSettings({
    this.isPublic = true,
    this.locationName = '',
    this.locationPoi,
    this.geoTagRef = '',
    this.visitedAt,
    this.circleIds = const <String>[],
    this.circleNames = const <String>[],
    this.homepage,
    this.summary = '',
    this.tagRefs = const <String>[],
    this.tagLabels = const <String>[],
    this.entityRefs = const <String>[],
    this.entityNames = const <String>[],
    this.assistantUsePolicy = AssistantUsePolicy.inherit,
    this.captureDisclosure = kDefaultCaptureDisclosure,
    this.captureMetadata = ExtractedMediaCaptureMetadata.empty,
  });

  final bool isPublic;
  final String locationName;

  /// 选中的页面位置数据；未选位置时为 null。
  ///
  /// Cloud wire 只在 `CreateLocationOption.fromWire` 边界进入页面模型，草稿不会
  /// 持久化生成契约对象，避免形成第二套 wire decoder。
  final CreateLocationOption? locationPoi;

  /// 由 [locationPoi] 解析出的行政区标签路径（`Topic/地理/行政区/...`）。
  ///
  /// 解析由 `GeoTagRefResolver` 经 tag-service 完成；解析不出时保持为空，
  /// 不用展示文本冒充标签。
  final String geoTagRef;

  /// 作者声明的实际到访时间（本地时区的日期选择结果）。
  ///
  /// 只在选了位置或关联主页时可声明：脱离地点的时间不构成「同地同期」事实。
  /// 未声明时保持 null，不用发布时间冒充到访时间。
  final DateTime? visitedAt;
  final List<String> circleIds;
  final List<String> circleNames;
  final HomepageCanonicalReference? homepage;
  final String summary;
  final List<String> tagRefs;
  final List<String> tagLabels;
  final List<String> entityRefs;
  final List<String> entityNames;
  final AssistantUsePolicy assistantUsePolicy;

  /// 创作者允许上报的拍摄元数据分组。默认四组全开。
  ///
  /// 关闭某组后，[ExtractedMediaCaptureMetadata.discloseOnly] 会在离开端侧前裁剪该组，
  /// 服务端据此撤回该组已派生的 tagRef 与交集事实。
  final Set<CaptureMetadataDisclosureGroup> captureDisclosure;

  /// 从首张素材解析出的拍摄事实，未解析到时为 [ExtractedMediaCaptureMetadata.empty]。
  ///
  /// 刻意不进 [toMap]：草稿不落 GPS 与拍摄时间这两项 PII，重新打开草稿时从素材
  /// 重新解析。落盘一份等于在本地多存一处 PII 副本，且撤回披露时要多清一处。
  final ExtractedMediaCaptureMetadata captureMetadata;

  /// 按当前披露设置裁剪后的拍摄事实。这是唯一允许离开端侧的形态。
  ExtractedMediaCaptureMetadata get disclosedCaptureMetadata =>
      captureMetadata.discloseOnly(captureDisclosure);

  /// 从 Map（如 _tabData）解析
  factory PublishSettings.fromMap(Map<String, dynamic> map) {
    final vis = (map['visibility']?.toString() ?? 'public').toLowerCase();
    CreateLocationOption? poi;
    final locRaw = map['location'];
    if (locRaw is Map && locRaw.isNotEmpty) {
      final m = Map<String, dynamic>.from(locRaw);
      final parsed = CreateLocationOption.fromMap(m);
      final hasCoords = parsed.latitude != 0 || parsed.longitude != 0;
      final hasLabel =
          parsed.name.trim().isNotEmpty ||
          (map['locationName'] as String? ?? '').trim().isNotEmpty;
      if (hasCoords || hasLabel) {
        final ln = (map['locationName'] as String? ?? '').trim();
        poi = parsed.name.trim().isEmpty && ln.isNotEmpty
            ? parsed.copyWith(name: ln)
            : parsed;
      }
    }
    return PublishSettings(
      isPublic: vis == 'public',
      locationName: (map['locationName'] as String? ?? '').trim(),
      locationPoi: poi,
      geoTagRef: (map['geoTagRef'] as String? ?? '').trim(),
      visitedAt: _visitedAtFromMap(map['visitedAt']),
      circleIds: vis == 'public'
          ? List<String>.from(map['circleIds'] as List? ?? const <String>[])
          : const <String>[],
      circleNames: vis == 'public'
          ? List<String>.from(map['circleNames'] as List? ?? const <String>[])
          : const <String>[],
      homepage: _homepageReferenceFromDraftMap(map['homepage']),
      summary: (map['summary'] as String? ?? '').trim(),
      tagRefs: List<String>.from(map['tagRefs'] as List? ?? const <String>[]),
      tagLabels: List<String>.from(
        map['tagLabels'] as List? ?? const <String>[],
      ),
      entityRefs: vis == 'public'
          ? List<String>.from(map['entityRefs'] as List? ?? const <String>[])
          : const <String>[],
      entityNames: vis == 'public'
          ? List<String>.from(map['entityNames'] as List? ?? const <String>[])
          : const <String>[],
      assistantUsePolicy: assistantUsePolicyFromWire(
        map['assistantUsePolicy'],
        'PublishSettings.assistantUsePolicy',
      ),
      captureDisclosure: _captureDisclosureFromMap(map['captureDisclosure']),
    );
  }

  /// 草稿恢复时解析到访时间。
  ///
  /// 草稿里存的是 RFC3339；解析不出时按未声明处理，不做任何猜测。
  static DateTime? _visitedAtFromMap(Object? raw) {
    if (raw is DateTime) return raw;
    final text = raw?.toString().trim() ?? '';
    if (text.isEmpty) return null;
    return DateTime.tryParse(text);
  }

  /// 草稿恢复时解析披露分组。
  ///
  /// 键缺失表示草稿早于本能力，按默认全开处理；显式空数组表示创作者关掉了全部分组，
  /// 必须原样尊重，不能回退成默认值。
  static Set<CaptureMetadataDisclosureGroup> _captureDisclosureFromMap(
    Object? raw,
  ) {
    if (raw is! List) return kDefaultCaptureDisclosure;
    return raw
        .map((item) => CaptureMetadataDisclosureGroup.fromWire(item.toString()))
        .nonNulls
        .toSet();
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
    'visibility': isPublic ? 'public' : 'private',
    'locationName': locationName,
    'location': locationPoi?.toMap() ?? <String, dynamic>{},
    'geoTagRef': geoTagRef,
    'visitedAt': visitedAt?.toIso8601String(),
    'circleIds': circleIds,
    'circleNames': circleNames,
    'homepage': _homepageReferenceToDraftMap(homepage),
    'summary': summary,
    'tagRefs': tagRefs,
    'tagLabels': tagLabels,
    'entityRefs': entityRefs,
    'entityNames': entityNames,
    'assistantUsePolicy': assistantUsePolicy.wireName,
    'captureDisclosure': captureDisclosure
        .map((group) => group.wire)
        .toList(growable: false),
  };

  /// 内容是否已绑定地点事实（选中 POI、解析出行政区标签或关联对象主页）。
  ///
  /// 到访时间只有挂在地点上才能参与「同地同期」交集，所以入口展示与 payload
  /// 落字段都以此为唯一判断。
  bool get hasPlaceAnchor =>
      locationPoi != null || geoTagRef.trim().isNotEmpty || homepage != null;

  /// 生成 Post 聚合的发布字段。
  ///
  /// [circleIds] 是跨上下文协调输入，只能在 Post 发布成功后交给
  /// CirclePostPlacement Command Facade，禁止写入 Post payload。
  Map<String, dynamic> toPayloadFields() {
    final payload = <String, dynamic>{
      'visibility': isPublic ? 'public' : 'private',
    };
    if (locationName.isNotEmpty) payload['locationName'] = locationName;
    if (geoTagRef.isNotEmpty) payload['geoTagRef'] = geoTagRef;
    if (hasPlaceAnchor && visitedAt != null) {
      payload['visitedAt'] = visitedAt!.toUtc().toIso8601String();
    }
    if (captureMetadata.isNotEmpty) {
      payload['captureDisclosure'] = captureDisclosure
          .intersection(captureMetadata.availableGroups)
          .map((group) => group.wire)
          .toList(growable: false);
    }
    if (locationPoi != null) {
      payload['location'] = <String, dynamic>{
        'latitude': locationPoi!.latitude,
        'longitude': locationPoi!.longitude,
      };
    }
    if (homepage != null) {
      payload.addAll(_homepageReferenceToPublicationFields(homepage!));
    }
    if (summary.trim().isNotEmpty) payload['summary'] = summary.trim();
    if (tagRefs.isNotEmpty) payload['tagRefs'] = tagRefs;
    if (entityRefs.isNotEmpty) payload['entityRefs'] = entityRefs;
    payload['assistantUsePolicy'] = assistantUsePolicy.wireName;
    return payload;
  }

  PublishSettings copyWith({
    bool? isPublic,
    String? locationName,
    CreateLocationOption? locationPoi,
    String? geoTagRef,
    DateTime? visitedAt,
    List<String>? circleIds,
    List<String>? circleNames,
    HomepageCanonicalReference? homepage,
    String? summary,
    List<String>? tagRefs,
    List<String>? tagLabels,
    List<String>? entityRefs,
    List<String>? entityNames,
    AssistantUsePolicy? assistantUsePolicy,
    Set<CaptureMetadataDisclosureGroup>? captureDisclosure,
    ExtractedMediaCaptureMetadata? captureMetadata,
    bool clearHomepage = false,
    bool clearLocationPoi = false,
    bool clearVisitedAt = false,
  }) => PublishSettings(
    isPublic: isPublic ?? this.isPublic,
    locationName: locationName ?? this.locationName,
    locationPoi: clearLocationPoi ? null : (locationPoi ?? this.locationPoi),
    geoTagRef: clearLocationPoi ? '' : (geoTagRef ?? this.geoTagRef),
    visitedAt: clearVisitedAt ? null : (visitedAt ?? this.visitedAt),
    circleIds: circleIds ?? this.circleIds,
    circleNames: circleNames ?? this.circleNames,
    homepage: clearHomepage ? null : (homepage ?? this.homepage),
    summary: summary ?? this.summary,
    tagRefs: tagRefs ?? this.tagRefs,
    tagLabels: tagLabels ?? this.tagLabels,
    entityRefs: entityRefs ?? this.entityRefs,
    entityNames: entityNames ?? this.entityNames,
    assistantUsePolicy: assistantUsePolicy ?? this.assistantUsePolicy,
    captureDisclosure: captureDisclosure ?? this.captureDisclosure,
    captureMetadata: captureMetadata ?? this.captureMetadata,
  );
}

/// 本地创作草稿的 Homepage ViewData codec。
///
/// 这是 App 本地持久化边界，不承担 Cloud wire 解码；Remote Homepage 仍只从
/// generated Homepage projection 经 typed mapper 进入 ViewData。
HomepageCanonicalReference? _homepageReferenceFromDraftMap(Object? raw) {
  if (raw is! Map) return null;
  final map = Map<String, dynamic>.from(raw);
  String? optionalString(String key) {
    final value = map[key]?.toString().trim() ?? '';
    return value.isEmpty ? null : value;
  }

  final id = map['id']?.toString().trim() ?? '';
  final homepageType = map['homepageType']?.toString().trim() ?? '';
  final title = map['title']?.toString().trim() ?? '';
  if (id.isEmpty || homepageType.isEmpty || title.isEmpty) return null;
  return HomepageCanonicalReference(
    id: id,
    homepageType: homepageType,
    title: title,
    subtitle: optionalString('subtitle'),
    coverUrl: optionalString('coverUrl'),
    status: optionalString('status'),
    canonicalEntityId: optionalString('canonicalEntityId'),
  );
}

Map<String, dynamic>? _homepageReferenceToDraftMap(
  HomepageCanonicalReference? reference,
) {
  if (reference == null) return null;
  return <String, dynamic>{
    'id': reference.id,
    'homepageType': reference.homepageType,
    'title': reference.title,
    if (reference.subtitle != null) 'subtitle': reference.subtitle,
    if (reference.coverUrl != null) 'coverUrl': reference.coverUrl,
    if (reference.status != null) 'status': reference.status,
    if (reference.canonicalEntityId != null)
      'canonicalEntityId': reference.canonicalEntityId,
  };
}

Map<String, dynamic> _homepageReferenceToPublicationFields(
  HomepageCanonicalReference reference,
) {
  return <String, dynamic>{
    'primaryHomepageId': reference.id,
    'primaryHomepageType': reference.homepageType,
    'primaryHomepageSnapshot': <String, dynamic>{
      'title': reference.title,
      if (reference.subtitle != null && reference.subtitle!.isNotEmpty)
        'subtitle': reference.subtitle,
      if (reference.coverUrl != null && reference.coverUrl!.isNotEmpty)
        'coverUrl': reference.coverUrl,
      if (reference.canonicalEntityId != null &&
          reference.canonicalEntityId!.isNotEmpty)
        'canonicalEntityId': reference.canonicalEntityId,
    },
  };
}

String homepageEntityRef(HomepageCanonicalReference reference) {
  final canonical = reference.canonicalEntityId?.trim() ?? '';
  return canonical;
}

class CreateLocationOption {
  const CreateLocationOption({
    this.id = '',
    required this.name,
    required this.latitude,
    required this.longitude,
    this.address = '',
    this.distanceMeters,
  });

  /// 从 Integration Location typed projection 构造页面选项。
  factory CreateLocationOption.fromWire(LocationPoi wire) =>
      CreateLocationOption(
        id: wire.id,
        name: wire.name,
        latitude: wire.latitude,
        longitude: wire.longitude,
        address: wire.address ?? '',
        distanceMeters: wire.distanceMeters,
      );

  /// 草稿本地 codec；只解析 App 自有 ViewData，不承担 Cloud wire 解码。
  factory CreateLocationOption.fromMap(Map<String, dynamic> map) =>
      CreateLocationOption(
        id: (map['id'] ?? '').toString().trim(),
        name: (map['name'] ?? '').toString().trim(),
        latitude: (map['latitude'] as num?)?.toDouble() ?? 0,
        longitude: (map['longitude'] as num?)?.toDouble() ?? 0,
        address: (map['address'] ?? '').toString().trim(),
        distanceMeters: (map['distanceMeters'] as num?)?.toInt(),
      );

  final String id;
  final String name;
  final double latitude;
  final double longitude;
  final String address;
  final int? distanceMeters;

  static const CreateLocationOption hidden = CreateLocationOption(
    id: '',
    name: '',
    latitude: 0,
    longitude: 0,
  );

  CreateLocationOption copyWith({String? name}) => CreateLocationOption(
    id: id,
    name: name ?? this.name,
    latitude: latitude,
    longitude: longitude,
    address: address,
    distanceMeters: distanceMeters,
  );

  Map<String, dynamic> toMap() => <String, dynamic>{
    'id': id,
    'name': name,
    'latitude': latitude,
    'longitude': longitude,
    if (address.isNotEmpty) 'address': address,
    if (distanceMeters != null) 'distanceMeters': distanceMeters,
  };

  Map<String, dynamic> toLocationMap() => <String, dynamic>{
    'latitude': latitude,
    'longitude': longitude,
  };
}

/// 圈子选项，用于发布时选择发布到哪些圈子。
/// [memberCount] 用于小字标注「X 人 · 已加入」；[recommendationReason] 用于推荐区「理由 · X 人」。
class CreateCircleOption {
  const CreateCircleOption({
    required this.id,
    required this.name,
    this.memberCount,
    this.postCount,
    this.coverUrl,
    this.recommendationReason,
    this.isJoined = true,
  });

  final String id;
  final String name;

  /// 成员数，用于小字标注。null 时显示「已加入」无数字。
  final int? memberCount;

  /// 创作数，用于与圈子列表保持统一的次级信息。
  final int? postCount;

  /// 圈子封面或头像，优先展示为方形封面缩略图。
  final String? coverUrl;

  /// 推荐理由，仅推荐区使用。如「与你兴趣相似」。
  final String? recommendationReason;

  /// true=已加入（可勾选发布），false=推荐加入（显示 + 关注）
  final bool isJoined;

  CreateCircleOption copyWith({
    String? id,
    String? name,
    int? memberCount,
    int? postCount,
    String? coverUrl,
    String? recommendationReason,
    bool? isJoined,
  }) => CreateCircleOption(
    id: id ?? this.id,
    name: name ?? this.name,
    memberCount: memberCount ?? this.memberCount,
    postCount: postCount ?? this.postCount,
    coverUrl: coverUrl ?? this.coverUrl,
    recommendationReason: recommendationReason ?? this.recommendationReason,
    isJoined: isJoined ?? this.isJoined,
  );
}
