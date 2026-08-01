// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/following_subject_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class ListFollowingSubjectsQuery {
  const ListFollowingSubjectsQuery({
    String? cursor,
    int limit = 20,
    FollowSubjectKind? subjectType,
  }) : cursor = cursor,
       limit = limit,
       subjectType = subjectType;

  final String? cursor;
  final int limit;
  final FollowSubjectKind? subjectType;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.subjectType != null) "subjectType": switch (this.subjectType!) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", },
  };
}

final class MarkFollowedSubjectVisitedCommand {
  MarkFollowedSubjectVisitedCommand({
    required String subjectId,
    required FollowSubjectKind subjectType,
    required DateTime visitedAt,
    String? clientRequestId,
  }) : subjectId = subjectId.trim(),
       subjectType = subjectType,
       visitedAt = visitedAt,
       clientRequestId = _normalizeGeneratedOptionalText(clientRequestId) {
    if (this.subjectId.isEmpty) {
      throw ArgumentError.value(this.subjectId, "subjectId", 'must not be blank');
    }
  }

  final String subjectId;
  final FollowSubjectKind subjectType;
  final DateTime visitedAt;
  final String? clientRequestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "subjectId": this.subjectId,
    "subjectType": switch (this.subjectType) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", },
    "visitedAt": this.visitedAt.toUtc().toIso8601String(),
    if (this.clientRequestId?.isNotEmpty == true) "clientRequestId": this.clientRequestId!,
  };
}

CloudOperationRequestPayload encodeUserFollowedSubjectVisitStateMarkFollowedSubjectVisitedGeneratedRequest(MarkFollowedSubjectVisitedCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subjectType": (switch (request.subjectType) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", }).toString(),
      "subjectId": request.subjectId,
    },
    body: <String, Object?>{
      "visitedAt": request.visitedAt.toUtc().toIso8601String(),
      if (request.clientRequestId?.isNotEmpty == true) "clientRequestId": request.clientRequestId!,
    },
  );
}

CloudOperationRequestPayload encodeUserFollowingSubjectListFollowingSubjectsGeneratedRequest(ListFollowingSubjectsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      if (request.subjectType != null) "subjectType": (switch (request.subjectType!) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", }).toString(),
    },
  );
}

