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

enum MapProviderType { baidu, amap }

class CreateLocationService {
  CreateLocationService({
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

  Future<List<CreateCircleOption>> listCircles(
    CircleRepository circleRepository,
  ) async {
    try {
      final result = await circleRepository.listCircles(limit: 20);
      if (result.isNotEmpty) {
        return result
            .map(
              (item) => CreateCircleOption(
                id: (item['id'] ?? '').toString(),
                name: (item['name'] ?? item['title'] ?? '').toString(),
                memberCount: _readCircleCount(
                  item['memberCount'] ?? item['member_count'],
                ),
                postCount: _readCircleCount(
                  item['postCount'] ?? item['post_count'],
                ),
                coverUrl: _readCircleCover(
                  item['coverUrl'] ?? item['cover'] ?? item['avatar'],
                ),
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

int? _readCircleCount(dynamic raw) {
  if (raw is int) {
    return raw;
  }
  if (raw is num) {
    return raw.toInt();
  }
  return int.tryParse((raw ?? '').toString());
}

String? _readCircleCover(dynamic raw) {
  final value = (raw ?? '').toString().trim();
  return value.isEmpty ? null : value;
}

const List<CreateCircleOption> _mockCircles = <CreateCircleOption>[
  CreateCircleOption(
    id: 'circle-photo',
    name: '摄影圈',
    memberCount: 123,
    postCount: 48,
    coverUrl:
        'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
  ),
  CreateCircleOption(
    id: 'circle-travel',
    name: '旅行圈',
    memberCount: 56,
    postCount: 31,
    coverUrl:
        'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600',
  ),
  CreateCircleOption(
    id: 'circle-food',
    name: '美食圈',
    memberCount: 89,
    postCount: 27,
    coverUrl:
        'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
  ),
  CreateCircleOption(
    id: 'circle-citywalk',
    name: 'CityWalk圈',
    memberCount: 234,
    postCount: 63,
    coverUrl:
        'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=400',
  ),
  CreateCircleOption(
    id: 'circle-video',
    name: '短视频创作圈',
    memberCount: 156,
    postCount: 72,
    coverUrl:
        'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?q=80&w=400',
  ),
  CreateCircleOption(
    id: 'circle-article',
    name: '图文写作圈',
    memberCount: 78,
    postCount: 45,
    coverUrl:
        'https://images.unsplash.com/photo-1455390582262-044cdead277a?q=80&w=400',
  ),
];

/// Mock 推荐圈子，用于选择页「推荐加入」区（design §3.7）
const List<CreateCircleOption> mockRecommendedCircles = <CreateCircleOption>[
  CreateCircleOption(
    id: 'rec-city',
    name: '城市探索',
    memberCount: 890,
    postCount: 126,
    coverUrl:
        'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=400',
    recommendationReason: '与你兴趣相似',
    isJoined: false,
  ),
  CreateCircleOption(
    id: 'rec-run',
    name: '跑步日记',
    memberCount: 312,
    postCount: 58,
    coverUrl:
        'https://images.unsplash.com/photo-1486218119243-13883505764c?q=80&w=400',
    recommendationReason: '同城热门',
    isJoined: false,
  ),
];
