// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

