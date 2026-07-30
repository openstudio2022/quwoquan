// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/author_impact_contracts.dart';

final class GetAuthorImpactQuery {
  const GetAuthorImpactQuery({
    required String personaId,
    int limit = 12,
  }) : personaId = personaId,
       limit = limit;

  final String personaId;
  final int limit;
}

final class ListAuthorImpactEvidenceQuery {
  const ListAuthorImpactEvidenceQuery({
    required String personaId,
    required String impactId,
    String? evidenceSnapshotId,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId,
       impactId = impactId,
       evidenceSnapshotId = evidenceSnapshotId,
       cursor = cursor,
       limit = limit;

  final String personaId;
  final String impactId;
  final String? evidenceSnapshotId;
  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeContentPostGetAuthorImpactGeneratedRequest(GetAuthorImpactQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeContentPostListAuthorImpactEvidenceGeneratedRequest(ListAuthorImpactEvidenceQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      "impactId": request.impactId,
      if (request.evidenceSnapshotId != null) "evidenceSnapshotId": request.evidenceSnapshotId!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

