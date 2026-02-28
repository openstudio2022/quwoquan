import 'dart:async';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/features/create/models/publish_settings_models.dart';

enum MapProviderType { baidu, amap }

class CreateLocationService {
  CreateLocationService({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  List<CreateLocationOption> _lastNearby = const <CreateLocationOption>[];
  List<CreateLocationOption> _lastSearch = const <CreateLocationOption>[];

  MapProviderType get currentProvider {
    final raw = CloudRuntimeConfig.mapProvider.toLowerCase().trim();
    if (raw == 'amap' || raw == 'ali' || raw == 'alimap') {
      return MapProviderType.amap;
    }
    return MapProviderType.baidu;
  }

  Future<List<CreateLocationOption>> nearby() async {
    final uri = Uri.parse('$_baseUrl/v1/integration/location/nearby').replace(
      queryParameters: <String, String>{
        // 当前云侧已支持默认中心点，端侧不感知供应商/定位实现细节。
        'limit': '20',
      },
    );

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

  Future<List<CreateLocationOption>> search(String keyword) async {
    final q = keyword.trim();
    if (q.isEmpty) {
      return nearby();
    }

    final uri = Uri.parse(
      '$_baseUrl/v1/integration/location/search',
    ).replace(queryParameters: <String, String>{'q': q, 'limit': '20'});

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
    final raw = decoded['items'];
    if (raw is! List) return const <CreateLocationOption>[];
    final result = <CreateLocationOption>[];
    for (final item in raw) {
      if (item is! Map) continue;
      final map = item.cast<String, dynamic>();
      final name = (map['name'] ?? '').toString().trim();
      final lat = (map['latitude'] as num?)?.toDouble();
      final lng = (map['longitude'] as num?)?.toDouble();
      if (name.isEmpty || lat == null || lng == null) continue;
      result.add(
        CreateLocationOption(
          name: name,
          latitude: lat,
          longitude: lng,
          address: (map['address'] ?? '').toString(),
          distanceMeters: (map['distanceMeters'] as num?)?.toInt(),
        ),
      );
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
  CreateCircleOption(id: 'circle-photo', name: '摄影圈'),
  CreateCircleOption(id: 'circle-travel', name: '旅行圈'),
  CreateCircleOption(id: 'circle-food', name: '美食圈'),
  CreateCircleOption(id: 'circle-citywalk', name: 'CityWalk圈'),
  CreateCircleOption(id: 'circle-video', name: '短视频创作圈'),
  CreateCircleOption(id: 'circle-article', name: '图文写作圈'),
];
