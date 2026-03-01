import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';

/// 通用发布设置状态模型（design B1），承载位置/公开/圈子选择，供创作、编辑等多页面复用。
class PublishSettings {
  const PublishSettings({
    this.isPublic = true,
    this.locationName = '',
    this.location = const <String, dynamic>{},
    this.circleIds = const <String>[],
    this.circleNames = const <String>[],
  });

  final bool isPublic;
  final String locationName;
  final Map<String, dynamic> location;
  final List<String> circleIds;
  final List<String> circleNames;

  /// 从 Map（如 _tabData）解析
  factory PublishSettings.fromMap(Map<String, dynamic> map) {
    final vis = (map['visibility']?.toString() ?? 'public').toLowerCase();
    return PublishSettings(
      isPublic: vis == 'public',
      locationName: (map['locationName'] as String? ?? '').trim(),
      location: Map<String, dynamic>.from(
        map['location'] as Map? ?? const <String, dynamic>{},
      ),
      circleIds: vis == 'public'
          ? List<String>.from(map['circleIds'] as List? ?? const <String>[])
          : const <String>[],
      circleNames: vis == 'public'
          ? List<String>.from(map['circleNames'] as List? ?? const <String>[])
          : const <String>[],
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
        'visibility': isPublic ? 'public' : 'private',
        'locationName': locationName,
        'location': location,
        'circleIds': circleIds,
        'circleNames': circleNames,
      };

  /// 生成发布 payload 字段
  Map<String, dynamic> toPayloadFields() {
    final payload = <String, dynamic>{
      'visibility': isPublic ? 'public' : 'private',
      'circleIds': circleIds,
    };
    if (locationName.isNotEmpty) payload['locationName'] = locationName;
    if (location.containsKey('latitude') && location.containsKey('longitude')) {
      payload['location'] = location;
    }
    return payload;
  }

  PublishSettings copyWith({
    bool? isPublic,
    String? locationName,
    Map<String, dynamic>? location,
    List<String>? circleIds,
    List<String>? circleNames,
  }) =>
      PublishSettings(
        isPublic: isPublic ?? this.isPublic,
        locationName: locationName ?? this.locationName,
        location: location ?? this.location,
        circleIds: circleIds ?? this.circleIds,
        circleNames: circleNames ?? this.circleNames,
      );
}

class CreateLocationOption {
  const CreateLocationOption({
    required this.name,
    required this.latitude,
    required this.longitude,
    this.address = '',
    this.distanceMeters,
  });

  /// 从 LocationPoiDto 构造，供 CreateLocationService 解析云响应时使用。
  factory CreateLocationOption.from(LocationPoiDto dto) => CreateLocationOption(
        name: dto.name,
        latitude: dto.latitude,
        longitude: dto.longitude,
        address: dto.address ?? '',
        distanceMeters: dto.distanceMeters,
      );

  final String name;
  final double latitude;
  final double longitude;
  final String address;
  final int? distanceMeters;

  static const CreateLocationOption hidden = CreateLocationOption(
    name: '',
    latitude: 0,
    longitude: 0,
  );

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
    this.recommendationReason,
    this.isJoined = true,
  });

  final String id;
  final String name;
  /// 成员数，用于小字标注。null 时显示「已加入」无数字。
  final int? memberCount;
  /// 推荐理由，仅推荐区使用。如「与你兴趣相似」。
  final String? recommendationReason;
  /// true=已加入（可勾选发布），false=推荐加入（显示 + 关注）
  final bool isJoined;

  CreateCircleOption copyWith({
    String? id,
    String? name,
    int? memberCount,
    String? recommendationReason,
    bool? isJoined,
  }) =>
      CreateCircleOption(
        id: id ?? this.id,
        name: name ?? this.name,
        memberCount: memberCount ?? this.memberCount,
        recommendationReason: recommendationReason ?? this.recommendationReason,
        isJoined: isJoined ?? this.isJoined,
      );
}
