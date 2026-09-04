// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 569af3dbf53fd87d5b5ae2ed6c0884ce37907db0b413b8f54bd21356e0284e11

library;

import '../operation_request_payload.dart';

part '../generated/requests/integration/integration_operation_contracts.g.requests.g.dart';

enum ConnectorAuthorizationMode {
  deviceNative("device_native"),
  oauth2("oauth2"),
  publicLink("public_link");

  const ConnectorAuthorizationMode(this.wireName);

  final String wireName;

  static ConnectorAuthorizationMode fromWire(Object? value, String path) {
    return switch (value) {
      "device_native" => ConnectorAuthorizationMode.deviceNative,
      "oauth2" => ConnectorAuthorizationMode.oauth2,
      "public_link" => ConnectorAuthorizationMode.publicLink,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConnectorConfirmationPolicy {
  none("none"),
  userConfirmation("user_confirmation");

  const ConnectorConfirmationPolicy(this.wireName);

  final String wireName;

  static ConnectorConfirmationPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "none" => ConnectorConfirmationPolicy.none,
      "user_confirmation" => ConnectorConfirmationPolicy.userConfirmation,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConnectorConnectionStatus {
  pending("pending"),
  active("active"),
  expired("expired"),
  revoked("revoked"),
  failed("failed");

  const ConnectorConnectionStatus(this.wireName);

  final String wireName;

  static ConnectorConnectionStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => ConnectorConnectionStatus.pending,
      "active" => ConnectorConnectionStatus.active,
      "expired" => ConnectorConnectionStatus.expired,
      "revoked" => ConnectorConnectionStatus.revoked,
      "failed" => ConnectorConnectionStatus.failed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConnectorDataClassification {
  public("public"),
  private("private"),
  sensitive("sensitive");

  const ConnectorDataClassification(this.wireName);

  final String wireName;

  static ConnectorDataClassification fromWire(Object? value, String path) {
    return switch (value) {
      "public" => ConnectorDataClassification.public,
      "private" => ConnectorDataClassification.private,
      "sensitive" => ConnectorDataClassification.sensitive,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConnectorDefinitionStatus {
  active("active"),
  retired("retired");

  const ConnectorDefinitionStatus(this.wireName);

  final String wireName;

  static ConnectorDefinitionStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => ConnectorDefinitionStatus.active,
      "retired" => ConnectorDefinitionStatus.retired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConnectorInvocationStatus {
  accepted("accepted"),
  awaitingConfirmation("awaiting_confirmation"),
  executing("executing"),
  completed("completed"),
  failed("failed"),
  cancelled("cancelled");

  const ConnectorInvocationStatus(this.wireName);

  final String wireName;

  static ConnectorInvocationStatus fromWire(Object? value, String path) {
    return switch (value) {
      "accepted" => ConnectorInvocationStatus.accepted,
      "awaiting_confirmation" => ConnectorInvocationStatus.awaitingConfirmation,
      "executing" => ConnectorInvocationStatus.executing,
      "completed" => ConnectorInvocationStatus.completed,
      "failed" => ConnectorInvocationStatus.failed,
      "cancelled" => ConnectorInvocationStatus.cancelled,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class ConnectorConnectionListSlice {
  const ConnectorConnectionListSlice({required this.items});

  final List<ConnectorConnectionView> items;

  factory ConnectorConnectionListSlice.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorConnectionListSlice",
  ]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ConnectorConnectionListSlice(
      items: List<ConnectorConnectionView>.unmodifiable(
        _requiredList(map["items"], '$path.items').asMap().entries.map(
          (entry) => ConnectorConnectionView.fromWire(
            _requiredObject(entry.value, '$path.items' + '[${entry.key}]'),
            '$path.items' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ConnectorConnectionMutationReceipt {
  const ConnectorConnectionMutationReceipt({
    required this.connection,
    required this.replayed,
  });

  final ConnectorConnectionView connection;
  final bool replayed;

  factory ConnectorConnectionMutationReceipt.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorConnectionMutationReceipt",
  ]) {
    _rejectUnknownFields(map, const <String>{"connection", "replayed"}, path);
    return ConnectorConnectionMutationReceipt(
      connection: ConnectorConnectionView.fromWire(
        _requiredObject(map["connection"], '$path.connection'),
        '$path.connection',
      ),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connection": connection.toWire(),
    "replayed": replayed,
  };
}

final class ConnectorConnectionView {
  const ConnectorConnectionView({
    required this.connectionId,
    required this.connectorId,
    required this.grantedCapabilities,
    required this.status,
    required this.freshnessAt,
    this.expiresAt,
    this.revokedAt,
    required this.revision,
    required this.createdAt,
    required this.updatedAt,
  });

  final String connectionId;
  final String connectorId;
  final List<String> grantedCapabilities;
  final ConnectorConnectionStatus status;
  final DateTime freshnessAt;
  final DateTime? expiresAt;
  final DateTime? revokedAt;
  final int revision;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory ConnectorConnectionView.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorConnectionView",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "connectionId",
      "connectorId",
      "grantedCapabilities",
      "status",
      "freshnessAt",
      "expiresAt",
      "revokedAt",
      "revision",
      "createdAt",
      "updatedAt",
    }, path);
    return ConnectorConnectionView(
      connectionId: _requiredNonBlankString(
        map["connectionId"],
        '$path.connectionId',
      ),
      connectorId: _requiredNonBlankString(
        map["connectorId"],
        '$path.connectorId',
      ),
      grantedCapabilities: List<String>.unmodifiable(
        _requiredList(
          map["grantedCapabilities"],
          '$path.grantedCapabilities',
        ).asMap().entries.map(
          (entry) => _requiredString(
            entry.value,
            '$path.grantedCapabilities' + '[${entry.key}]',
          ),
        ),
      ),
      status: ConnectorConnectionStatus.fromWire(map["status"], '$path.status'),
      freshnessAt: _requiredTimestamp(map["freshnessAt"], '$path.freshnessAt'),
      expiresAt: map["expiresAt"] == null
          ? null
          : _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
      revokedAt: map["revokedAt"] == null
          ? null
          : _requiredTimestamp(map["revokedAt"], '$path.revokedAt'),
      revision: _requiredInt(map["revision"], '$path.revision'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connectionId": connectionId,
    "connectorId": connectorId,
    "grantedCapabilities": grantedCapabilities
        .map((value) => value)
        .toList(growable: false),
    "status": status.wireName,
    "freshnessAt": freshnessAt.toUtc().toIso8601String(),
    if (expiresAt != null) "expiresAt": expiresAt!.toUtc().toIso8601String(),
    if (revokedAt != null) "revokedAt": revokedAt!.toUtc().toIso8601String(),
    "revision": revision,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class ConnectorDefinition {
  const ConnectorDefinition({
    required this.connectorId,
    required this.displayName,
    required this.description,
    required this.capabilities,
    required this.authorizationMode,
    required this.confirmationPolicy,
    required this.dataClassification,
    required this.supportedSurfaceKinds,
    required this.status,
    required this.releaseDigest,
    required this.publishedAt,
  });

  final String connectorId;
  final String displayName;
  final String description;
  final List<String> capabilities;
  final ConnectorAuthorizationMode authorizationMode;
  final ConnectorConfirmationPolicy confirmationPolicy;
  final ConnectorDataClassification dataClassification;
  final List<String> supportedSurfaceKinds;
  final ConnectorDefinitionStatus status;
  final String releaseDigest;
  final DateTime publishedAt;

  factory ConnectorDefinition.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorDefinition",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "connectorId",
      "displayName",
      "description",
      "capabilities",
      "authorizationMode",
      "confirmationPolicy",
      "dataClassification",
      "supportedSurfaceKinds",
      "status",
      "releaseDigest",
      "publishedAt",
    }, path);
    return ConnectorDefinition(
      connectorId: _requiredNonBlankString(
        map["connectorId"],
        '$path.connectorId',
      ),
      displayName: _requiredNonBlankString(
        map["displayName"],
        '$path.displayName',
      ),
      description: _requiredString(map["description"], '$path.description'),
      capabilities: List<String>.unmodifiable(
        _requiredList(
          map["capabilities"],
          '$path.capabilities',
        ).asMap().entries.map(
          (entry) => _requiredString(
            entry.value,
            '$path.capabilities' + '[${entry.key}]',
          ),
        ),
      ),
      authorizationMode: ConnectorAuthorizationMode.fromWire(
        map["authorizationMode"],
        '$path.authorizationMode',
      ),
      confirmationPolicy: ConnectorConfirmationPolicy.fromWire(
        map["confirmationPolicy"],
        '$path.confirmationPolicy',
      ),
      dataClassification: ConnectorDataClassification.fromWire(
        map["dataClassification"],
        '$path.dataClassification',
      ),
      supportedSurfaceKinds: List<String>.unmodifiable(
        _requiredList(
          map["supportedSurfaceKinds"],
          '$path.supportedSurfaceKinds',
        ).asMap().entries.map(
          (entry) => _requiredString(
            entry.value,
            '$path.supportedSurfaceKinds' + '[${entry.key}]',
          ),
        ),
      ),
      status: ConnectorDefinitionStatus.fromWire(map["status"], '$path.status'),
      releaseDigest: _requiredString(
        map["releaseDigest"],
        '$path.releaseDigest',
      ),
      publishedAt: _requiredTimestamp(map["publishedAt"], '$path.publishedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "connectorId": connectorId,
    "displayName": displayName,
    "description": description,
    "capabilities": capabilities.map((value) => value).toList(growable: false),
    "authorizationMode": authorizationMode.wireName,
    "confirmationPolicy": confirmationPolicy.wireName,
    "dataClassification": dataClassification.wireName,
    "supportedSurfaceKinds": supportedSurfaceKinds
        .map((value) => value)
        .toList(growable: false),
    "status": status.wireName,
    "releaseDigest": releaseDigest,
    "publishedAt": publishedAt.toUtc().toIso8601String(),
  };
}

final class ConnectorDefinitionListSlice {
  const ConnectorDefinitionListSlice({required this.items});

  final List<ConnectorDefinition> items;

  factory ConnectorDefinitionListSlice.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorDefinitionListSlice",
  ]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ConnectorDefinitionListSlice(
      items: List<ConnectorDefinition>.unmodifiable(
        _requiredList(map["items"], '$path.items').asMap().entries.map(
          (entry) => ConnectorDefinition.fromWire(
            _requiredObject(entry.value, '$path.items' + '[${entry.key}]'),
            '$path.items' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ConnectorInvocationListSlice {
  const ConnectorInvocationListSlice({required this.items});

  final List<ConnectorInvocationView> items;

  factory ConnectorInvocationListSlice.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorInvocationListSlice",
  ]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ConnectorInvocationListSlice(
      items: List<ConnectorInvocationView>.unmodifiable(
        _requiredList(map["items"], '$path.items').asMap().entries.map(
          (entry) => ConnectorInvocationView.fromWire(
            _requiredObject(entry.value, '$path.items' + '[${entry.key}]'),
            '$path.items' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ConnectorInvocationView {
  const ConnectorInvocationView({
    required this.invocationId,
    required this.connectionId,
    required this.capability,
    required this.status,
    this.continuationRef,
    this.normalizedFailureCode,
    required this.recoveryAction,
    required this.revision,
    required this.createdAt,
    required this.updatedAt,
    this.completedAt,
  });

  final String invocationId;
  final String connectionId;
  final String capability;
  final ConnectorInvocationStatus status;
  final String? continuationRef;
  final String? normalizedFailureCode;
  final String recoveryAction;
  final int revision;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? completedAt;

  factory ConnectorInvocationView.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectorInvocationView",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "invocationId",
      "connectionId",
      "capability",
      "status",
      "continuationRef",
      "normalizedFailureCode",
      "recoveryAction",
      "revision",
      "createdAt",
      "updatedAt",
      "completedAt",
    }, path);
    return ConnectorInvocationView(
      invocationId: _requiredNonBlankString(
        map["invocationId"],
        '$path.invocationId',
      ),
      connectionId: _requiredNonBlankString(
        map["connectionId"],
        '$path.connectionId',
      ),
      capability: _requiredNonBlankString(
        map["capability"],
        '$path.capability',
      ),
      status: ConnectorInvocationStatus.fromWire(map["status"], '$path.status'),
      continuationRef: map["continuationRef"] == null
          ? null
          : _requiredString(map["continuationRef"], '$path.continuationRef'),
      normalizedFailureCode: map["normalizedFailureCode"] == null
          ? null
          : _requiredString(
              map["normalizedFailureCode"],
              '$path.normalizedFailureCode',
            ),
      recoveryAction: _requiredString(
        map["recoveryAction"],
        '$path.recoveryAction',
      ),
      revision: _requiredInt(map["revision"], '$path.revision'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      completedAt: map["completedAt"] == null
          ? null
          : _requiredTimestamp(map["completedAt"], '$path.completedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "invocationId": invocationId,
    "connectionId": connectionId,
    "capability": capability,
    "status": status.wireName,
    if (continuationRef != null) "continuationRef": continuationRef!,
    if (normalizedFailureCode != null)
      "normalizedFailureCode": normalizedFailureCode!,
    "recoveryAction": recoveryAction,
    "revision": revision,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (completedAt != null)
      "completedAt": completedAt!.toUtc().toIso8601String(),
  };
}

final class LocationPoi {
  const LocationPoi({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
    this.address,
    this.distanceMeters,
  });

  final String id;
  final String name;
  final double latitude;
  final double longitude;
  final String? address;
  final int? distanceMeters;

  factory LocationPoi.fromWire(
    Map<String, Object?> map, [
    String path = "LocationPoi",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "id",
      "name",
      "latitude",
      "longitude",
      "address",
      "distanceMeters",
    }, path);
    return LocationPoi(
      id: _requiredNonBlankString(map["id"], '$path.id'),
      name: _requiredNonBlankString(map["name"], '$path.name'),
      latitude: _requiredDouble(map["latitude"], '$path.latitude'),
      longitude: _requiredDouble(map["longitude"], '$path.longitude'),
      address: map["address"] == null
          ? null
          : _requiredString(map["address"], '$path.address'),
      distanceMeters: map["distanceMeters"] == null
          ? null
          : _requiredInt(map["distanceMeters"], '$path.distanceMeters'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "name": name,
    "latitude": latitude,
    "longitude": longitude,
    if (address != null) "address": address!,
    if (distanceMeters != null) "distanceMeters": distanceMeters!,
  };
}

final class LocationPoiListSlice {
  const LocationPoiListSlice({required this.items});

  final List<LocationPoi> items;

  factory LocationPoiListSlice.fromWire(
    Map<String, Object?> map, [
    String path = "LocationPoiListSlice",
  ]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return LocationPoiListSlice(
      items: List<LocationPoi>.unmodifiable(
        _requiredList(map["items"], '$path.items').asMap().entries.map(
          (entry) => LocationPoi.fromWire(
            _requiredObject(entry.value, '$path.items' + '[${entry.key}]'),
            '$path.items' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

ConnectorConnectionListSlice decodeConnectorConnectionListSlice(
  Object? response,
) => ConnectorConnectionListSlice.fromWire(
  _requiredObject(response, "ConnectorConnectionListSlice"),
  "ConnectorConnectionListSlice",
);

ConnectorConnectionMutationReceipt decodeConnectorConnectionMutationReceipt(
  Object? response,
) => ConnectorConnectionMutationReceipt.fromWire(
  _requiredObject(response, "ConnectorConnectionMutationReceipt"),
  "ConnectorConnectionMutationReceipt",
);

ConnectorConnectionView decodeConnectorConnectionView(Object? response) =>
    ConnectorConnectionView.fromWire(
      _requiredObject(response, "ConnectorConnectionView"),
      "ConnectorConnectionView",
    );

ConnectorDefinition decodeConnectorDefinition(Object? response) =>
    ConnectorDefinition.fromWire(
      _requiredObject(response, "ConnectorDefinition"),
      "ConnectorDefinition",
    );

ConnectorDefinitionListSlice decodeConnectorDefinitionListSlice(
  Object? response,
) => ConnectorDefinitionListSlice.fromWire(
  _requiredObject(response, "ConnectorDefinitionListSlice"),
  "ConnectorDefinitionListSlice",
);

ConnectorInvocationListSlice decodeConnectorInvocationListSlice(
  Object? response,
) => ConnectorInvocationListSlice.fromWire(
  _requiredObject(response, "ConnectorInvocationListSlice"),
  "ConnectorInvocationListSlice",
);

ConnectorInvocationView decodeConnectorInvocationView(Object? response) =>
    ConnectorInvocationView.fromWire(
      _requiredObject(response, "ConnectorInvocationView"),
      "ConnectorInvocationView",
    );

LocationPoiListSlice decodeLocationPoiListSlice(Object? response) =>
    LocationPoiListSlice.fromWire(
      _requiredObject(response, "LocationPoiListSlice"),
      "LocationPoiListSlice",
    );

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException(
      '$path contains unknown fields: ${unknown.join(', ')}',
    );
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
