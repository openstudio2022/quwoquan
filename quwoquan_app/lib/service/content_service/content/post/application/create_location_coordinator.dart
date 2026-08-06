import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/location_query_contracts.dart';
import 'package:quwoquan_app/runtime/platform/location/location_gateway.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';

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

  List<CreateLocationOption> _lastNearby = const <CreateLocationOption>[];
  List<CreateLocationOption> _lastSearch = const <CreateLocationOption>[];

  Future<LocationAccessResult> ensureLocationAccess() =>
      locationGateway.ensureAccess();

  Future<List<CreateLocationOption>> nearby({
    double? latitude,
    double? longitude,
  }) async {
    try {
      final slice = await nearbyReader.getNearbyLocations(
        NearbyLocationQueryParams(latitude: latitude, longitude: longitude),
      );
      final items = slice.items
          .map(CreateLocationOption.fromWire)
          .toList(growable: false);
      if (items.isNotEmpty) {
        _lastNearby = items;
        _lastSearch = items;
      }
      return items;
    } on CloudException catch (error) {
      if (error.statusCode == 429 && _lastNearby.isNotEmpty) {
        return _lastNearby;
      }
      rethrow;
    }
  }

  Future<List<CreateLocationOption>> search(
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
      final items = slice.items
          .map(CreateLocationOption.fromWire)
          .toList(growable: false);
      if (items.isNotEmpty) {
        _lastSearch = items;
      }
      return items;
    } on CloudException catch (error) {
      if (error.statusCode == 429 && _lastSearch.isNotEmpty) {
        return _lastSearch;
      }
      rethrow;
    }
  }
}
