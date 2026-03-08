import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/core/services/location_permission_checker.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

// 兼容导出，供页面使用
export 'package:quwoquan_app/core/services/location_permission_checker.dart'
    show LocationPermissionResult;

enum MapProviderType { baidu, amap }

class CreateLocationService {
  CreateLocationService({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
    LocationPermissionChecker? locationPermissionChecker,
  })  : _httpClient =
            httpClient ?? CloudHttpClient(client: client ?? http.Client()),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
        _locationPermissionChecker =
            locationPermissionChecker ?? const GeolocatorLocationPermissionChecker();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final LocationPermissionChecker _locationPermissionChecker;
  List<CreateLocationOption> _lastNearby = const <CreateLocationOption>[];
  List<CreateLocationOption> _lastSearch = const <CreateLocationOption>[];

  MapProviderType get currentProvider {
    final raw = CloudRuntimeConfig.mapProvider.toLowerCase().trim();
    if (raw == 'amap' || raw == 'ali' || raw == 'alimap') {
      return MapProviderType.amap;
    }
    return MapProviderType.baidu;
  }

  /// 检查并请求定位权限，返回权限状态；若已授予则返回当前位置。
  Future<({LocationPermissionResult result, Position? position})>
      ensureLocationPermission() =>
          _locationPermissionChecker.ensureLocationPermission();

  /// 打开应用权限设置页面。
  Future<bool> openAppSettings() =>
      _locationPermissionChecker.openAppSettings();

  Future<List<CreateLocationOption>> nearby({
    double? lat,
    double? lng,
  }) async {
    final params = <String, String>{'limit': '20'};
    if (lat != null && lng != null) {
      params['lat'] = lat.toString();
      params['lng'] = lng.toString();
    }
    final uri = Uri.parse('$_baseUrl${IntegrationLocationMetadata.nearbyPath}')
        .replace(queryParameters: params);

    try {
      final decoded = await _httpClient.getJson(
        uri,
        headers: CloudRequestHeaders.forPage('create.location.nearby'),
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
    final uri = Uri.parse('$_baseUrl${IntegrationLocationMetadata.searchPath}')
        .replace(queryParameters: params);

    try {
      final decoded = await _httpClient.getJson(
        uri,
        headers: CloudRequestHeaders.forPage('create.location.search'),
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

  List<CreateLocationOption> _parseItems(dynamic decoded) {
    if (decoded is! Map<String, dynamic>) return const <CreateLocationOption>[];
    final raw = decoded[IntegrationLocationMetadata.responseItemsKey];
    if (raw is! List) return const <CreateLocationOption>[];
    final result = <CreateLocationOption>[];
    for (final item in raw) {
      if (item is! Map) continue;
      try {
        final dto = LocationPoiDto.fromMap(item.cast<String, dynamic>());
        if (dto.name.trim().isEmpty) continue;
        result.add(CreateLocationOption.from(dto));
      } catch (_) {
        continue;
      }
    }
    return result;
  }
}

class CreateCircleService {
  const CreateCircleService();

  Future<List<CreateCircleOption>> listCircles(DataService dataService) async {
    try {
      final result = await dataService.getDataList(
        endpoint: '/circles',
        limit: 20,
      );
      if (result.isNotEmpty) {
        return result
            .map(
              (item) => CreateCircleOption(
                id: (item['id'] ?? '').toString(),
                name: (item['name'] ?? item['title'] ?? '').toString(),
                memberCount: item['memberCount'] is int
                    ? item['memberCount'] as int
                    : item['member_count'] is int
                        ? item['member_count'] as int
                        : null,
              ),
            )
            .where((item) => item.id.isNotEmpty && item.name.isNotEmpty)
            .toList();
      }
    } catch (_) {
      // ignore and fallback
    }
    return _mockCircles;
  }
}

const List<CreateCircleOption> _mockCircles = <CreateCircleOption>[
  CreateCircleOption(id: 'circle-photo', name: '摄影圈', memberCount: 123),
  CreateCircleOption(id: 'circle-travel', name: '旅行圈', memberCount: 56),
  CreateCircleOption(id: 'circle-food', name: '美食圈', memberCount: 89),
  CreateCircleOption(id: 'circle-citywalk', name: 'CityWalk圈', memberCount: 234),
  CreateCircleOption(id: 'circle-video', name: '短视频创作圈', memberCount: 156),
  CreateCircleOption(id: 'circle-article', name: '图文写作圈', memberCount: 78),
];

/// Mock 推荐圈子，用于选择页「推荐加入」区（design §3.7）
const List<CreateCircleOption> mockRecommendedCircles = <CreateCircleOption>[
  CreateCircleOption(
    id: 'rec-city',
    name: '城市探索',
    memberCount: 890,
    recommendationReason: '与你兴趣相似',
    isJoined: false,
  ),
  CreateCircleOption(
    id: 'rec-run',
    name: '跑步日记',
    memberCount: 312,
    recommendationReason: '同城热门',
    isJoined: false,
  ),
];
