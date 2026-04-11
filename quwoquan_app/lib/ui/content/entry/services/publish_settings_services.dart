import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:meta/meta.dart';
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

  List<CreateLocationOption> _parseItems(Object? decoded) =>
      CreateLocationService.parseIntegrationLocationItems(decoded);

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

/// 仅 `AppDataSourceMode.mock` 下由发布确认页展示；Remote/Release 默认不传（见 [CreatePage]）。
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
