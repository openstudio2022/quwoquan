// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: fa62066656f839f0ca9a27a7521397df0ff2acaa1ab3e869a807832c920adfce

part of '../../../integration/integration_operation_contracts.g.dart';

void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}

String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}

int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

double _generatedRequestDouble(Object? value, String path) {
  if (value is num) return value.toDouble();
  throw FormatException('$path must be a number');
}

List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class CreateConnectorConnectionRequest {
  CreateConnectorConnectionRequest({
    required String connectorId,
    required List<String> requestedCapabilities,
    required String grantReceiptRef,
  }) : connectorId = connectorId,
       requestedCapabilities = List.unmodifiable(requestedCapabilities),
       grantReceiptRef = grantReceiptRef {
    if (this.connectorId.isEmpty) {
      throw ArgumentError.value(
        this.connectorId,
        "connectorId",
        'must not be blank',
      );
    }
    if (this.grantReceiptRef.isEmpty) {
      throw ArgumentError.value(
        this.grantReceiptRef,
        "grantReceiptRef",
        'must not be blank',
      );
    }
  }

  final String connectorId;
  final List<String> requestedCapabilities;
  final String grantReceiptRef;

  factory CreateConnectorConnectionRequest.fromWire(
    Map<String, Object?> map, [
    String path = "CreateConnectorConnectionRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "connectorId",
      "requestedCapabilities",
      "grantReceiptRef",
    }, path);
    return CreateConnectorConnectionRequest(
      connectorId: _generatedRequestString(
        map["connectorId"],
        '$path.connectorId',
      ),
      requestedCapabilities: List<String>.unmodifiable(
        _generatedRequestList(
          map["requestedCapabilities"],
          '$path.requestedCapabilities',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.requestedCapabilities' + '[${entry.key}]',
          ),
        ),
      ),
      grantReceiptRef: _generatedRequestString(
        map["grantReceiptRef"],
        '$path.grantReceiptRef',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connectorId": this.connectorId,
    "requestedCapabilities": this.requestedCapabilities
        .map((value) => value)
        .toList(growable: false),
    "grantReceiptRef": this.grantReceiptRef,
  };
}

final class GetConnectorConnectionQuery {
  GetConnectorConnectionQuery({required String connectionId})
    : connectionId = connectionId {
    if (this.connectionId.isEmpty) {
      throw ArgumentError.value(
        this.connectionId,
        "connectionId",
        'must not be blank',
      );
    }
  }

  final String connectionId;

  factory GetConnectorConnectionQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetConnectorConnectionQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "connectionId",
    }, path);
    return GetConnectorConnectionQuery(
      connectionId: _generatedRequestString(
        map["connectionId"],
        '$path.connectionId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connectionId": this.connectionId,
  };
}

final class GetConnectorDefinitionQuery {
  GetConnectorDefinitionQuery({required String connectorId})
    : connectorId = connectorId {
    if (this.connectorId.isEmpty) {
      throw ArgumentError.value(
        this.connectorId,
        "connectorId",
        'must not be blank',
      );
    }
  }

  final String connectorId;

  factory GetConnectorDefinitionQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetConnectorDefinitionQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "connectorId",
    }, path);
    return GetConnectorDefinitionQuery(
      connectorId: _generatedRequestString(
        map["connectorId"],
        '$path.connectorId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connectorId": this.connectorId,
  };
}

final class GetConnectorInvocationQuery {
  GetConnectorInvocationQuery({required String invocationId})
    : invocationId = invocationId {
    if (this.invocationId.isEmpty) {
      throw ArgumentError.value(
        this.invocationId,
        "invocationId",
        'must not be blank',
      );
    }
  }

  final String invocationId;

  factory GetConnectorInvocationQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetConnectorInvocationQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "invocationId",
    }, path);
    return GetConnectorInvocationQuery(
      invocationId: _generatedRequestString(
        map["invocationId"],
        '$path.invocationId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "invocationId": this.invocationId,
  };
}

final class ListConnectorConnectionsQuery {
  ListConnectorConnectionsQuery({int? limit}) : limit = limit {
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final int? limit;

  factory ListConnectorConnectionsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListConnectorConnectionsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"limit"}, path);
    return ListConnectorConnectionsQuery(
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.limit != null) "limit": this.limit!,
  };
}

final class ListConnectorDefinitionsQuery {
  ListConnectorDefinitionsQuery({String? capability, int? limit})
    : capability = capability,
      limit = limit {
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? capability;
  final int? limit;

  factory ListConnectorDefinitionsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListConnectorDefinitionsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "capability",
      "limit",
    }, path);
    return ListConnectorDefinitionsQuery(
      capability: map["capability"] == null
          ? null
          : _generatedRequestString(map["capability"], '$path.capability'),
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.capability != null) "capability": this.capability!,
    if (this.limit != null) "limit": this.limit!,
  };
}

final class ListConnectorInvocationsQuery {
  ListConnectorInvocationsQuery({String? connectionId, int? limit})
    : connectionId = connectionId,
      limit = limit {
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? connectionId;
  final int? limit;

  factory ListConnectorInvocationsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListConnectorInvocationsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "connectionId",
      "limit",
    }, path);
    return ListConnectorInvocationsQuery(
      connectionId: map["connectionId"] == null
          ? null
          : _generatedRequestString(map["connectionId"], '$path.connectionId'),
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.connectionId != null) "connectionId": this.connectionId!,
    if (this.limit != null) "limit": this.limit!,
  };
}

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

  factory LocationSearchQueryParams.fromWire(
    Map<String, Object?> map, [
    String path = "LocationSearchQueryParams",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "q",
      "cityCode",
      "lat",
      "lng",
      "limit",
    }, path);
    return LocationSearchQueryParams(
      query: _generatedRequestString(map["q"], '$path.q'),
      cityCode: map["cityCode"] == null
          ? null
          : _generatedRequestString(map["cityCode"], '$path.cityCode'),
      latitude: map["lat"] == null
          ? null
          : _generatedRequestDouble(map["lat"], '$path.lat'),
      longitude: map["lng"] == null
          ? null
          : _generatedRequestDouble(map["lng"], '$path.lng'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
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

  factory NearbyLocationQueryParams.fromWire(
    Map<String, Object?> map, [
    String path = "NearbyLocationQueryParams",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "lat",
      "lng",
      "radiusMeters",
      "limit",
    }, path);
    return NearbyLocationQueryParams(
      latitude: map["lat"] == null
          ? null
          : _generatedRequestDouble(map["lat"], '$path.lat'),
      longitude: map["lng"] == null
          ? null
          : _generatedRequestDouble(map["lng"], '$path.lng'),
      radiusMeters: map["radiusMeters"] == null
          ? null
          : _generatedRequestInt(map["radiusMeters"], '$path.radiusMeters'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.latitude != null) "lat": this.latitude!,
    if (this.longitude != null) "lng": this.longitude!,
    if (this.radiusMeters != null) "radiusMeters": this.radiusMeters!,
    "limit": this.limit,
  };
}

final class RevokeConnectorConnectionRequest {
  RevokeConnectorConnectionRequest({
    required String connectionId,
    required int expectedRevision,
  }) : connectionId = connectionId,
       expectedRevision = expectedRevision {
    if (this.connectionId.isEmpty) {
      throw ArgumentError.value(
        this.connectionId,
        "connectionId",
        'must not be blank',
      );
    }
    if (this.expectedRevision <= 0) {
      throw ArgumentError.value(
        this.expectedRevision,
        "expectedRevision",
        "must be positive",
      );
    }
  }

  final String connectionId;
  final int expectedRevision;

  factory RevokeConnectorConnectionRequest.fromWire(
    Map<String, Object?> map, [
    String path = "RevokeConnectorConnectionRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "connectionId",
      "expectedRevision",
    }, path);
    return RevokeConnectorConnectionRequest(
      connectionId: _generatedRequestString(
        map["connectionId"],
        '$path.connectionId',
      ),
      expectedRevision: _generatedRequestInt(
        map["expectedRevision"],
        '$path.expectedRevision',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connectionId": this.connectionId,
    "expectedRevision": this.expectedRevision,
  };
}

CloudOperationRequestPayload
encodeIntegrationConnectorConnectionCreateConnectorConnectionGeneratedRequest(
  CreateConnectorConnectionRequest request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "connectorId": request.connectorId,
      "requestedCapabilities": request.requestedCapabilities
          .map((value) => value)
          .toList(growable: false),
      "grantReceiptRef": request.grantReceiptRef,
    },
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorConnectionGetConnectorConnectionGeneratedRequest(
  GetConnectorConnectionQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"connectionId": request.connectionId},
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorConnectionListConnectorConnectionsGeneratedRequest(
  ListConnectorConnectionsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorConnectionRevokeConnectorConnectionGeneratedRequest(
  RevokeConnectorConnectionRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"connectionId": request.connectionId},
    body: <String, Object?>{"expectedRevision": request.expectedRevision},
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorDefinitionGetConnectorDefinitionGeneratedRequest(
  GetConnectorDefinitionQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"connectorId": request.connectorId},
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorDefinitionListConnectorDefinitionsGeneratedRequest(
  ListConnectorDefinitionsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.capability != null) "capability": request.capability!,
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorInvocationGetConnectorInvocationGeneratedRequest(
  GetConnectorInvocationQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"invocationId": request.invocationId},
  );
}

CloudOperationRequestPayload
encodeIntegrationConnectorInvocationListConnectorInvocationsGeneratedRequest(
  ListConnectorInvocationsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.connectionId != null) "connectionId": request.connectionId!,
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeIntegrationLocationGetNearbyLocationsGeneratedRequest(
  NearbyLocationQueryParams request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.latitude != null) "lat": (request.latitude!).toString(),
      if (request.longitude != null) "lng": (request.longitude!).toString(),
      if (request.radiusMeters != null)
        "radiusMeters": (request.radiusMeters!).toString(),
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeIntegrationLocationSearchLocationsGeneratedRequest(
  LocationSearchQueryParams request,
) {
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
