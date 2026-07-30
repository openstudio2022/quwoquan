// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../integration/location_queries.dart';

final class LocationSearchQueryParams {
  const LocationSearchQueryParams({
    required String query,
    String? cityCode,
    double? latitude,
    double? longitude,
    int limit = 20,
  }) : query = query,
       cityCode = cityCode,
       latitude = latitude,
       longitude = longitude,
       limit = limit;

  final String query;
  final String? cityCode;
  final double? latitude;
  final double? longitude;
  final int limit;
}

final class NearbyLocationQueryParams {
  const NearbyLocationQueryParams({
    double? latitude,
    double? longitude,
    int? radiusMeters,
    int limit = 20,
  }) : latitude = latitude,
       longitude = longitude,
       radiusMeters = radiusMeters,
       limit = limit;

  final double? latitude;
  final double? longitude;
  final int? radiusMeters;
  final int limit;
}

CloudOperationRequestPayload encodeIntegrationLocationGetNearbyLocationsGeneratedRequest(NearbyLocationQueryParams request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.latitude != null) "lat": (request.latitude!).toString(),
      if (request.longitude != null) "lng": (request.longitude!).toString(),
      if (request.radiusMeters != null) "radiusMeters": (request.radiusMeters!).toString(),
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeIntegrationLocationSearchLocationsGeneratedRequest(LocationSearchQueryParams request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "q": request.query,
      if (request.cityCode?.isNotEmpty == true) "cityCode": request.cityCode!,
      if (request.latitude != null) "lat": (request.latitude!).toString(),
      if (request.longitude != null) "lng": (request.longitude!).toString(),
      "limit": (request.limit).toString(),
    },
  );
}

