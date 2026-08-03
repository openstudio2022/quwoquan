import 'package:quwoquan_app/cloud/services/integration/location_query_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

final class AlphaLocationQueryAdapter
    implements NearbyLocationReader, LocationSearchReader {
  AlphaLocationQueryAdapter({ObjectScenarioSeedReader? fixtures})
    : _items = _readItems(fixtures ?? objectScenarioSeedReader);

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

  static List<LocationPoi> _readItems(ObjectScenarioSeedReader fixtures) {
    final decoded = fixtures.document('integration');
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map) {
      throw FormatException('Integration alpha fixture seedSets is missing');
    }
    final locationSeed = seedSets['location_poi_core'];
    if (locationSeed is! Map || locationSeed['pois'] is! List) {
      throw FormatException('Integration location_poi_core fixture is missing');
    }
    final items = <LocationPoi>[];
    for (final raw in locationSeed['pois'] as List) {
      if (raw is! Map) {
        throw FormatException('Integration POI fixture must be an object');
      }
      final map = Map<String, dynamic>.from(raw);
      final id = (map['poiId'] ?? '').toString().trim();
      final name = (map['name'] ?? '').toString().trim();
      final latitude = map['lat'];
      final longitude = map['lng'];
      if (id.isEmpty || name.isEmpty || latitude is! num || longitude is! num) {
        throw FormatException('Integration POI fixture is incomplete');
      }
      items.add(
        LocationPoi(
          id: id,
          name: name,
          latitude: latitude.toDouble(),
          longitude: longitude.toDouble(),
          address: map['address']?.toString(),
          distanceMeters: (map['distanceMeters'] as num?)?.toInt(),
        ),
      );
    }
    return List<LocationPoi>.unmodifiable(items);
  }
}
