import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/integration/mock/integration_mock_data.dart';

abstract class IntegrationRepository {
  Future<List<LocationPoiDto>> getNearbyLocations({
    double? latitude,
    double? longitude,
    int? radiusMeters,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<LocationPoiDto>> searchLocations({
    required String query,
    String? cityCode,
    double? latitude,
    double? longitude,
    int limit = CloudApiDefaults.pageLimit,
  });
}

class MockIntegrationRepository implements IntegrationRepository {
  const MockIntegrationRepository();

  @override
  Future<List<LocationPoiDto>> getNearbyLocations({
    double? latitude,
    double? longitude,
    int? radiusMeters,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final items = IntegrationMockData.locationPois
        .map(LocationPoiDto.fromMap)
        .toList(growable: false);
    items.sort((left, right) {
      final leftDistance = left.distanceMeters ?? 1 << 20;
      final rightDistance = right.distanceMeters ?? 1 << 20;
      return leftDistance.compareTo(rightDistance);
    });
    return items.take(limit).toList(growable: false);
  }

  @override
  Future<List<LocationPoiDto>> searchLocations({
    required String query,
    String? cityCode,
    double? latitude,
    double? longitude,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    final items = IntegrationMockData.locationPois
        .where((item) {
          if (normalizedQuery.isEmpty) {
            return true;
          }
          final name = (item['name'] ?? '').toString().toLowerCase();
          final address = (item['address'] ?? '').toString().toLowerCase();
          return name.contains(normalizedQuery) ||
              address.contains(normalizedQuery);
        })
        .map(LocationPoiDto.fromMap)
        .toList(growable: false);
    items.sort((left, right) {
      final leftDistance = left.distanceMeters ?? 1 << 20;
      final rightDistance = right.distanceMeters ?? 1 << 20;
      return leftDistance.compareTo(rightDistance);
    });
    return items.take(limit).toList(growable: false);
  }
}

class RemoteIntegrationRepository implements IntegrationRepository {
  RemoteIntegrationRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(client: http.Client()),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Map<String, String> _headersForSurface({
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  String _contextForSurface({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      operationId: operationId,
    );
  }

  @override
  Future<List<LocationPoiDto>> getNearbyLocations({
    double? latitude,
    double? longitude,
    int? radiusMeters,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(
        IntegrationApiMetadata.getNearbyLocationsPath,
        queryParameters: <String, String>{
          if (latitude != null) 'lat': '$latitude',
          if (longitude != null) 'lng': '$longitude',
          if (radiusMeters != null) 'radiusMeters': '$radiusMeters',
          'limit': '$limit',
        },
      ),
      headers: _headersForSurface(
        operationId: IntegrationApiMetadata.getNearbyLocationsOperation,
        clientPageId: IntegrationRequestPageIds.getNearbyLocations,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        operationId: IntegrationApiMetadata.getNearbyLocationsOperation,
      ),
    );
    return page.items
        .map(LocationPoiDto.fromMap)
        .where((item) => item.name.trim().isNotEmpty)
        .toList(growable: false);
  }

  @override
  Future<List<LocationPoiDto>> searchLocations({
    required String query,
    String? cityCode,
    double? latitude,
    double? longitude,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(
        IntegrationApiMetadata.searchLocationsPath,
        queryParameters: <String, String>{
          'q': query,
          if (cityCode != null && cityCode.isNotEmpty) 'cityCode': cityCode,
          if (latitude != null) 'lat': '$latitude',
          if (longitude != null) 'lng': '$longitude',
          'limit': '$limit',
        },
      ),
      headers: _headersForSurface(
        operationId: IntegrationApiMetadata.searchLocationsOperation,
        clientPageId: IntegrationRequestPageIds.searchLocations,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        operationId: IntegrationApiMetadata.searchLocationsOperation,
      ),
    );
    return page.items
        .map(LocationPoiDto.fromMap)
        .where((item) => item.name.trim().isNotEmpty)
        .toList(growable: false);
  }
}
