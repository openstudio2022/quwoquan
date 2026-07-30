// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

