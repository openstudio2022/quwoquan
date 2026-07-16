import 'dart:convert';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/src/generated/alpha_fixture_bundle.g.dart';

final class AlphaLocationQueryAdapter
    implements NearbyLocationReader, LocationSearchReader {
  AlphaLocationQueryAdapter({AlphaFixtureBundle bundle = alphaFixtureBundle})
    : _items = _readItems(bundle);

  final List<LocationPoiDto> _items;

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) async {
    return LocationPoiListSlice(
      _items.take(query.limit).toList(growable: false),
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
      matches.take(query.limit).toList(growable: false),
    );
  }

  static List<LocationPoiDto> _readItems(AlphaFixtureBundle bundle) {
    final asset = bundle.assets['integration'];
    if (asset == null) {
      throw StateError('Integration alpha fixture asset is missing');
    }
    final decoded = jsonDecode(asset.sourceJson);
    if (decoded is! Map) {
      throw FormatException('Integration alpha fixture root must be an object');
    }
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map) {
      throw FormatException('Integration alpha fixture seedSets is missing');
    }
    final locationSeed = seedSets['location_poi_core'];
    if (locationSeed is! Map || locationSeed['pois'] is! List) {
      throw FormatException('Integration location_poi_core fixture is missing');
    }
    final items = <LocationPoiDto>[];
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
        LocationPoiDto(
          id: id,
          name: name,
          latitude: latitude.toDouble(),
          longitude: longitude.toDouble(),
          address: map['address']?.toString(),
          distanceMeters: (map['distanceMeters'] as num?)?.toInt(),
        ),
      );
    }
    return List<LocationPoiDto>.unmodifiable(items);
  }
}
