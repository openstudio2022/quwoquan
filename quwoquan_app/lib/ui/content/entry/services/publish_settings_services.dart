import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/app_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/services/location_permission_checker.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

// 兼容导出，供页面使用
export 'package:quwoquan_app/core/services/location_permission_checker.dart'
    show LocationPermissionResult;

/// 发布选点服务接口（content/entry 领域）。
///
/// 三层模式（对齐 `01-arch-constraints` §2.2、`08-mock-data-isolation`）：
/// - [CreateLocationService]：抽象接口，UI 只依赖此类型；
/// - [RemoteCreateLocationService]：经 gateway/API + 系统定位的真实实现；
/// - [MockCreateLocationService]：本地 canonical POI，不发 HTTP、不依赖系统定位，
///   供 alpha/mock 模式使用，杜绝「附近地点访问失败」断点。
///
/// 切换由 `createLocationServiceProvider` 依据 `appDataSourceModeProvider` 完成，
/// UI 不得直接实例化 Remote/Mock。
abstract class CreateLocationService {
  /// 检查并请求定位权限，返回权限状态；若已授予则返回当前位置。
  Future<({LocationPermissionResult result, Position? position})>
  ensureLocationPermission();

  /// 打开应用权限设置页面。
  Future<bool> openAppSettings();

  /// 附近地点。
  Future<List<CreateLocationOption>> nearby({double? lat, double? lng});

  /// 关键字检索地点；空关键字回退到 [nearby]。
  Future<List<CreateLocationOption>> search(
    String keyword, {
    double? lat,
    double? lng,
  });

  /// JSON 解析边界：非法类型返回空列表，不抛异常。
  @visibleForTesting
  static List<CreateLocationOption> parseIntegrationLocationItems(
    Object? decoded,
  ) {
    if (decoded is! Map) return const <CreateLocationOption>[];
    final decodedMap = Map<String, dynamic>.from(decoded);
    final raw = decodedMap[IntegrationLocationMetadata.responseItemsKey];
    if (raw is! List) return const <CreateLocationOption>[];
    final result = <CreateLocationOption>[];
    for (final item in raw) {
      if (item is! Map) continue;
      try {
        final dto = LocationPoiDto.fromMap(Map<String, dynamic>.from(item));
        if (dto.name.trim().isEmpty) continue;
        result.add(CreateLocationOption.from(dto));
      } catch (_) {
        continue;
      }
    }
    return result;
  }
}

class RemoteCreateLocationService implements CreateLocationService {
  RemoteCreateLocationService({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
    LocationPermissionChecker? locationPermissionChecker,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _locationPermissionChecker =
           locationPermissionChecker ??
           const GeolocatorLocationPermissionChecker();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final LocationPermissionChecker _locationPermissionChecker;
  List<CreateLocationOption> _lastNearby = const <CreateLocationOption>[];
  List<CreateLocationOption> _lastSearch = const <CreateLocationOption>[];

  /// 检查并请求定位权限，返回权限状态；若已授予则返回当前位置。
  @override
  Future<({LocationPermissionResult result, Position? position})>
  ensureLocationPermission() =>
      _locationPermissionChecker.ensureLocationPermission();

  /// 打开应用权限设置页面。
  @override
  Future<bool> openAppSettings() =>
      _locationPermissionChecker.openAppSettings();

  @override
  Future<List<CreateLocationOption>> nearby({double? lat, double? lng}) async {
    final params = <String, String>{'limit': '20'};
    if (lat != null && lng != null) {
      params['lat'] = lat.toString();
      params['lng'] = lng.toString();
    }
    final uri = Uri.parse(
      '$_baseUrl${IntegrationLocationMetadata.nearbyPath}',
    ).replace(queryParameters: params);

    try {
      final decoded = await _httpClient.getJson(
        uri,
        headers: CloudRequestHeaders.forPage(
          AppRequestPageIds.createLocationNearby,
        ),
      );
      final items = _parseItems(decoded);
      if (items.isNotEmpty) {
        _lastNearby = items;
        _lastSearch = items;
      }
      return items;
    } on CloudException catch (e) {
      if (e.statusCode == 429 && _lastNearby.isNotEmpty) {
        return _lastNearby;
      }
      rethrow;
    }
  }

  @override
  Future<List<CreateLocationOption>> search(
    String keyword, {
    double? lat,
    double? lng,
  }) async {
    final q = keyword.trim();
    if (q.isEmpty) {
      return nearby(lat: lat, lng: lng);
    }

    final params = <String, String>{'q': q, 'limit': '20'};
    if (lat != null && lng != null) {
      params['lat'] = lat.toString();
      params['lng'] = lng.toString();
    }
    final uri = Uri.parse(
      '$_baseUrl${IntegrationLocationMetadata.searchPath}',
    ).replace(queryParameters: params);

    try {
      final decoded = await _httpClient.getJson(
        uri,
        headers: CloudRequestHeaders.forPage(
          AppRequestPageIds.createLocationSearch,
        ),
      );
      final items = _parseItems(decoded);
      if (items.isNotEmpty) {
        _lastSearch = items;
      }
      return items;
    } on CloudException catch (e) {
      if (e.statusCode == 429 && _lastSearch.isNotEmpty) {
        return _lastSearch;
      }
      rethrow;
    }
  }

  List<CreateLocationOption> _parseItems(Object? decoded) =>
      CreateLocationService.parseIntegrationLocationItems(decoded);
}

/// 本地 mock 选点服务：不发 HTTP、不依赖系统定位。
///
/// alpha / mock 模式下使用，确保「附近位置」始终有可选项，避免因网关或地图密钥
/// 缺失导致的整页「附近地点访问失败」。数据为 canonical POI，仅存在于本 Mock 实现内
/// （对齐 `08-mock-data-isolation`：假数据只存在于 Mock 实现或 test/）。
class MockCreateLocationService implements CreateLocationService {
  MockCreateLocationService();

  static const List<CreateLocationOption> _canonicalNearby =
      <CreateLocationOption>[
    CreateLocationOption(
      id: 'mock_poi_tianfu_square',
      name: '天府广场',
      latitude: 30.6586,
      longitude: 104.0648,
      address: '成都市青羊区',
      distanceMeters: 120,
    ),
    CreateLocationOption(
      id: 'mock_poi_taikoo_li',
      name: '成都远洋太古里',
      latitude: 30.6548,
      longitude: 104.0839,
      address: '成都市锦江区中纱帽街',
      distanceMeters: 480,
    ),
    CreateLocationOption(
      id: 'mock_poi_chunxi_road',
      name: '春熙路',
      latitude: 30.6520,
      longitude: 104.0817,
      address: '成都市锦江区',
      distanceMeters: 650,
    ),
    CreateLocationOption(
      id: 'mock_poi_jinli',
      name: '锦里古街',
      latitude: 30.6420,
      longitude: 104.0480,
      address: '成都市武侯区武侯祠大街',
      distanceMeters: 1500,
    ),
    CreateLocationOption(
      id: 'mock_poi_dujiangyan',
      name: '都江堰景区',
      latitude: 31.0026,
      longitude: 103.6171,
      address: '成都市都江堰市公园路',
      distanceMeters: 48000,
    ),
  ];

  static final Position _mockPosition = Position(
    latitude: 30.6586,
    longitude: 104.0648,
    timestamp: DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    accuracy: 0,
    altitude: 0,
    altitudeAccuracy: 0,
    heading: 0,
    headingAccuracy: 0,
    speed: 0,
    speedAccuracy: 0,
  );

  @override
  Future<({LocationPermissionResult result, Position? position})>
  ensureLocationPermission() async =>
      (result: LocationPermissionResult.granted, position: _mockPosition);

  @override
  Future<bool> openAppSettings() async => true;

  @override
  Future<List<CreateLocationOption>> nearby({double? lat, double? lng}) async =>
      _canonicalNearby;

  @override
  Future<List<CreateLocationOption>> search(
    String keyword, {
    double? lat,
    double? lng,
  }) async {
    final q = keyword.trim();
    if (q.isEmpty) return _canonicalNearby;
    final matched = _canonicalNearby
        .where(
          (poi) =>
              poi.name.contains(q) ||
              poi.address.contains(q),
        )
        .toList(growable: false);
    return matched;
  }
}

class CreateCircleService {
  const CreateCircleService();

  Future<List<CreateCircleOption>> listCircles(
    CircleRepository circleRepository,
  ) async {
    try {
      final result = await circleRepository.listCircles(limit: 20);
      if (result.isNotEmpty) {
        final out = <CreateCircleOption>[];
        for (final dto in result) {
          if (dto.id.isEmpty || dto.name.isEmpty) continue;
          out.add(CreateCircleOption.fromCircleDto(dto));
        }
        if (out.isNotEmpty) return out;
      }
    } catch (_) {
      // ignore and fallback
    }
    return const <CreateCircleOption>[];
  }
}

/// 发布确认页推荐圈：数据来自 [CircleRepository.publishFlowRecommendedCircles]（内嵌目录有值，云侧为空）。
List<CreateCircleOption> publishFlowRecommendedCircleOptions(CircleRepository circles) {
  final dtos = circles.publishFlowRecommendedCircles();
  if (dtos.isEmpty) return const <CreateCircleOption>[];
  const reasons = <String, String>{
    'rec-city': '与你兴趣相似',
    'rec-run': '同城热门',
  };
  return dtos
      .map(
        (dto) => CreateCircleOption.fromCircleDto(
          dto,
          isJoined: false,
          recommendationReason: reasons[dto.id],
        ),
      )
      .toList(growable: false);
}
