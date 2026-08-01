// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/contact_discovery_contracts.dart';

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class DismissContactDiscoveryCommand {
  DismissContactDiscoveryCommand({
    required String discoveryId,
  }) : discoveryId = discoveryId.trim() {
    if (this.discoveryId.isEmpty) {
      throw ArgumentError.value(this.discoveryId, "discoveryId", 'must not be blank');
    }
  }

  final String discoveryId;

  Map<String, Object?> toJson() => <String, Object?>{
    "id": this.discoveryId,
  };
}

final class GetLatestContactDiscoveryQuery {
  const GetLatestContactDiscoveryQuery();
}

final class InitiateContactDiscoveryCommand {
  InitiateContactDiscoveryCommand({
    required List<String> hashedPhones,
  }) : hashedPhones = _normalizeGeneratedTextList(hashedPhones, deduplicate: false) {
  }

  final List<String> hashedPhones;

  Map<String, Object?> toJson() => <String, Object?>{
    "hashedPhones": this.hashedPhones.map((value) => value).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeUserContactDiscoveryRecordDismissContactDiscoveryGeneratedRequest(DismissContactDiscoveryCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "id": request.discoveryId,
    },
  );
}

CloudOperationRequestPayload encodeUserContactDiscoveryRecordGetLatestContactDiscoveryGeneratedRequest(GetLatestContactDiscoveryQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserContactDiscoveryRecordInitiateContactDiscoveryGeneratedRequest(InitiateContactDiscoveryCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "hashedPhones": request.hashedPhones.map((value) => value).toList(growable: false),
    },
  );
}

