import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/integration/location_query_contracts.dart';

final class FakeLocationQueryAdapter
    implements NearbyLocationReader, LocationSearchReader {
  FakeLocationQueryAdapter({this.items = const <LocationPoiDto>[], this.error});

  final List<LocationPoiDto> items;
  final Object? error;

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) async {
    _throwIfConfigured();
    return LocationPoiListSlice(
      items.take(query.limit).toList(growable: false),
    );
  }

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    _throwIfConfigured();
    final normalized = query.query.trim().toLowerCase();
    return LocationPoiListSlice(
      items
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
