import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';

/// 通用发布设置状态模型（design B1），承载位置/公开/圈子选择，供创作、编辑等多页面复用。
class PublishSettings {
  const PublishSettings({
    this.isPublic = true,
    this.locationName = '',
    this.locationPoi,
    this.circleIds = const <String>[],
    this.circleNames = const <String>[],
    this.homepage,
  });

  final bool isPublic;
  final String locationName;

  /// 选中 POI（codegen [LocationPoiDto]）；未选位置时为 null。
  final LocationPoiDto? locationPoi;
  final List<String> circleIds;
  final List<String> circleNames;
  final HomepageCanonicalReference? homepage;

  /// 从 Map（如 _tabData）解析
  factory PublishSettings.fromMap(Map<String, dynamic> map) {
    final vis = (map['visibility']?.toString() ?? 'public').toLowerCase();
    LocationPoiDto? poi;
    final locRaw = map['location'];
    if (locRaw is Map && locRaw.isNotEmpty) {
      final m = Map<String, dynamic>.from(locRaw);
      final parsed = LocationPoiDto.fromMap(m);
      final hasCoords =
          parsed.latitude != 0 || parsed.longitude != 0;
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
      circleIds: vis == 'public'
          ? List<String>.from(map['circleIds'] as List? ?? const <String>[])
          : const <String>[],
      circleNames: vis == 'public'
          ? List<String>.from(map['circleNames'] as List? ?? const <String>[])
          : const <String>[],
      homepage: map['homepage'] is Map
          ? HomepageCanonicalReference.fromMap(
              Map<String, dynamic>.from(map['homepage'] as Map),
            )
          : null,
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
    'visibility': isPublic ? 'public' : 'private',
    'locationName': locationName,
    'location': locationPoi?.toMap() ?? <String, dynamic>{},
    'circleIds': circleIds,
    'circleNames': circleNames,
    'homepage': homepage?.toMap(),
  };

  /// 生成发布 payload 字段
  Map<String, dynamic> toPayloadFields() {
    final payload = <String, dynamic>{
      'visibility': isPublic ? 'public' : 'private',
      'circleIds': circleIds,
    };
    if (locationName.isNotEmpty) payload['locationName'] = locationName;
    if (locationPoi != null) {
      payload['location'] = <String, dynamic>{
        'latitude': locationPoi!.latitude,
        'longitude': locationPoi!.longitude,
      };
    }
    if (homepage != null) {
      payload.addAll(homepage!.toPayloadFields());
    }
    return payload;
  }

  PublishSettings copyWith({
    bool? isPublic,
    String? locationName,
    LocationPoiDto? locationPoi,
    List<String>? circleIds,
    List<String>? circleNames,
    HomepageCanonicalReference? homepage,
    bool clearHomepage = false,
    bool clearLocationPoi = false,
  }) => PublishSettings(
    isPublic: isPublic ?? this.isPublic,
    locationName: locationName ?? this.locationName,
    locationPoi: clearLocationPoi
        ? null
        : (locationPoi ?? this.locationPoi),
    circleIds: circleIds ?? this.circleIds,
    circleNames: circleNames ?? this.circleNames,
    homepage: clearHomepage ? null : (homepage ?? this.homepage),
  );
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

  /// 从 LocationPoiDto 构造，供 CreateLocationService 解析云响应时使用。
  factory CreateLocationOption.from(LocationPoiDto dto) => CreateLocationOption(
    id: dto.id,
    name: dto.name,
    latitude: dto.latitude,
    longitude: dto.longitude,
    address: dto.address ?? '',
    distanceMeters: dto.distanceMeters,
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

  LocationPoiDto toLocationPoiDto() {
    final syntheticId = id.trim().isNotEmpty
        ? id.trim()
        : 'local_${latitude}_$longitude';
    return LocationPoiDto(
      id: syntheticId,
      name: name,
      latitude: latitude,
      longitude: longitude,
      address: address.isEmpty ? null : address,
      distanceMeters: distanceMeters,
    );
  }

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

  factory CreateCircleOption.fromCircleDto(
    CircleDto dto, {
    bool isJoined = true,
    String? recommendationReason,
  }) {
    return CreateCircleOption(
      id: dto.id,
      name: dto.name,
      memberCount: dto.memberCount,
      postCount: dto.postCount,
      coverUrl: dto.coverUrl,
      isJoined: isJoined,
      recommendationReason: recommendationReason,
    );
  }

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
