import '../operation_request_payload.dart';
part '../generated/requests/integration/location_queries.requests.g.dart';

/// Typed location projection shared by Remote and alpha adapters.
final class LocationPoiDto {
  const LocationPoiDto({
    this.id = '',
    this.name = '',
    this.latitude = 0,
    this.longitude = 0,
    this.address,
    this.distanceMeters,
  });

  final String id;
  final String name;
  final double latitude;
  final double longitude;
  final String? address;
  final int? distanceMeters;

  factory LocationPoiDto.fromMap(Map<String, Object?> map) {
    return LocationPoiDto(
      id: (map['id'] ?? '').toString(),
      name: (map['name'] ?? '').toString(),
      latitude: (map['latitude'] as num?)?.toDouble() ?? 0,
      longitude: (map['longitude'] as num?)?.toDouble() ?? 0,
      address: map['address']?.toString() ?? '',
      distanceMeters: (map['distanceMeters'] as num?)?.toInt(),
    );
  }

  Map<String, Object?> toMap() => <String, Object?>{
    'id': id,
    'name': name,
    'latitude': latitude,
    'longitude': longitude,
    'address': address,
    'distanceMeters': distanceMeters,
  };

  LocationPoiDto copyWith({
    String? id,
    String? name,
    double? latitude,
    double? longitude,
    String? address,
    int? distanceMeters,
  }) {
    return LocationPoiDto(
      id: id ?? this.id,
      name: name ?? this.name,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
      address: address ?? this.address,
      distanceMeters: distanceMeters ?? this.distanceMeters,
    );
  }
}





final class LocationPoiListSlice {
  LocationPoiListSlice(Iterable<LocationPoiDto> items)
    : items = List<LocationPoiDto>.unmodifiable(items);

  final List<LocationPoiDto> items;
}

abstract interface class NearbyLocationReader {
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  );
}

abstract interface class LocationSearchReader {
  Future<LocationPoiListSlice> searchLocations(LocationSearchQueryParams query);
}





LocationPoiListSlice decodeLocationPoiListSlice(Object? response) {
  if (response is! Map<Object?, Object?>) {
    throw const FormatException('Location response must be an object');
  }
  final items = response['items'];
  if (items is! List<Object?>) {
    throw const FormatException('Location response.items must be a list');
  }
  return LocationPoiListSlice(
    items.map((item) {
      if (item is! Map<Object?, Object?>) {
        throw const FormatException('Location item must be an object');
      }
      final id = item['id'];
      final name = item['name'];
      final latitude = item['latitude'];
      final longitude = item['longitude'];
      final address = item['address'];
      final distanceMeters = item['distanceMeters'];
      if (id is! String || id.trim().isEmpty) {
        throw const FormatException('Location item.id must be a string');
      }
      if (name is! String || name.trim().isEmpty) {
        throw const FormatException('Location item.name must be a string');
      }
      if (latitude is! num || longitude is! num) {
        throw const FormatException(
          'Location item coordinates must be numeric',
        );
      }
      if (address != null && address is! String) {
        throw const FormatException('Location item.address must be a string');
      }
      if (distanceMeters != null && distanceMeters is! num) {
        throw const FormatException(
          'Location item.distanceMeters must be numeric',
        );
      }
      return LocationPoiDto(
        id: id,
        name: name,
        latitude: latitude.toDouble(),
        longitude: longitude.toDouble(),
        address: address as String?,
        distanceMeters: (distanceMeters as num?)?.toInt(),
      );
    }),
  );
}
