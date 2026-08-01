// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/author_impact_contracts.dart';

final class GetAuthorImpactQuery {
  const GetAuthorImpactQuery({
    required String personaId,
    int limit = 12,
  }) : personaId = personaId,
       limit = limit;

  final String personaId;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    "limit": this.limit,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    "impactId": this.impactId,
    if (this.evidenceSnapshotId != null) "evidenceSnapshotId": this.evidenceSnapshotId!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
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

