import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/location_query_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class LocationQueryTypedDouble
    implements NearbyLocationReader, LocationSearchReader {
  LocationQueryTypedDouble({List<LocationPoi>? items})
    : _items = List<LocationPoi>.unmodifiable(items ?? _defaultItems);

  final List<LocationPoi> _items;

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) async {
    return LocationPoiListSlice(
      items: _items.take(query.limit).toList(growable: false),
    );
  }

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    final normalized = query.query.trim().toLowerCase();
    final matches = _items.where((item) {
      if (normalized.isEmpty) return true;
      return item.name.toLowerCase().contains(normalized) ||
          (item.address ?? '').toLowerCase().contains(normalized);
    });
    return LocationPoiListSlice(
      items: matches.take(query.limit).toList(growable: false),
    );
  }

  static const List<LocationPoi> _defaultItems = <LocationPoi>[
    LocationPoi(
      id: 'fixture_poi_west_lake',
      name: '杭州西湖',
      latitude: 30.2431,
      longitude: 120.1505,
      address: '浙江省杭州市西湖区',
    ),
    LocationPoi(
      id: 'fixture_poi_coffee',
      name: '契约咖啡馆',
      latitude: 30.25,
      longitude: 120.16,
      address: '杭州市测试路 1 号',
    ),
  ];
}
