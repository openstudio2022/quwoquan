import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/integration/location_query_contracts.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';

/// 创作选点的跨边界编排：组合 Integration query 与端侧定位能力。
final class CreateLocationCoordinator {
  CreateLocationCoordinator({
    required this.nearbyReader,
    required this.searchReader,
    required this.locationGateway,
  });

  final NearbyLocationReader nearbyReader;
  final LocationSearchReader searchReader;
  final LocationGateway locationGateway;

  List<LocationPoiDto> _lastNearby = const <LocationPoiDto>[];
  List<LocationPoiDto> _lastSearch = const <LocationPoiDto>[];

  Future<LocationAccessResult> ensureLocationAccess() =>
      locationGateway.ensureAccess();

  Future<List<LocationPoiDto>> nearby({
    double? latitude,
    double? longitude,
  }) async {
    try {
      final slice = await nearbyReader.getNearbyLocations(
        NearbyLocationQueryParams(latitude: latitude, longitude: longitude),
      );
      if (slice.items.isNotEmpty) {
        _lastNearby = slice.items;
        _lastSearch = slice.items;
      }
      return slice.items;
    } on CloudException catch (error) {
      if (error.statusCode == 429 && _lastNearby.isNotEmpty) {
        return _lastNearby;
      }
      rethrow;
    }
  }

  Future<List<LocationPoiDto>> search(
    String keyword, {
    double? latitude,
    double? longitude,
  }) async {
    final normalized = keyword.trim();
    if (normalized.isEmpty) {
      return nearby(latitude: latitude, longitude: longitude);
    }
    try {
      final slice = await searchReader.searchLocations(
        LocationSearchQueryParams(
          query: normalized,
          latitude: latitude,
          longitude: longitude,
        ),
      );
      if (slice.items.isNotEmpty) {
        _lastSearch = slice.items;
      }
      return slice.items;
    } on CloudException catch (error) {
      if (error.statusCode == 429 && _lastSearch.isNotEmpty) {
        return _lastSearch;
      }
      rethrow;
    }
  }
}
