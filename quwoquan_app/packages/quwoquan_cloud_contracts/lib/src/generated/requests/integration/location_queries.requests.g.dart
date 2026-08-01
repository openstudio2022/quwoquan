// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "q": this.query,
    if (this.cityCode?.isNotEmpty == true) "cityCode": this.cityCode!,
    if (this.latitude != null) "lat": this.latitude!,
    if (this.longitude != null) "lng": this.longitude!,
    "limit": this.limit,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.latitude != null) "lat": this.latitude!,
    if (this.longitude != null) "lng": this.longitude!,
    if (this.radiusMeters != null) "radiusMeters": this.radiusMeters!,
    "limit": this.limit,
  };
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

