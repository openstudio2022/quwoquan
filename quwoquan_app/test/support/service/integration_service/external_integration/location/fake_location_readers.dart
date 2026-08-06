import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/location_query_contracts.dart';

final class FakeLocationQueryAdapter
    implements NearbyLocationReader, LocationSearchReader {
  FakeLocationQueryAdapter({this.items = const <LocationPoi>[], this.error});

  final List<LocationPoi> items;
  final Object? error;

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) async {
    _throwIfConfigured();
    return LocationPoiListSlice(
      items: items.take(query.limit).toList(growable: false),
    );
  }

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    _throwIfConfigured();
    final normalized = query.query.trim().toLowerCase();
    return LocationPoiListSlice(
      items: items
          .where(
            (item) =>
                normalized.isEmpty ||
                item.name.toLowerCase().contains(normalized) ||
                (item.address ?? '').toLowerCase().contains(normalized),
          )
          .take(query.limit)
          .toList(growable: false),
    );
  }

  void _throwIfConfigured() {
    final configuredError = error;
    if (configuredError != null) {
      throw configuredError;
    }
  }
}
