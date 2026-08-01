// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/subject_follow_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class FollowSubjectCommand {
  FollowSubjectCommand({
    required FollowSubjectKind subjectType,
    required String subjectId,
    String? source,
  }) : subjectType = subjectType,
       subjectId = subjectId.trim(),
       source = _normalizeGeneratedOptionalText(source) {
    if (this.subjectId.isEmpty) {
      throw ArgumentError.value(this.subjectId, "subjectId", 'must not be blank');
    }
  }

  final FollowSubjectKind subjectType;
  final String subjectId;
  final String? source;

  Map<String, Object?> toJson() => <String, Object?>{
    "subjectType": switch (this.subjectType) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", },
    "subjectId": this.subjectId,
    if (this.source != null) "source": this.source!,
  };
}

final class UnfollowSubjectCommand {
  UnfollowSubjectCommand({
    required FollowSubjectKind subjectType,
    required String subjectId,
  }) : subjectType = subjectType,
       subjectId = subjectId.trim() {
    if (this.subjectId.isEmpty) {
      throw ArgumentError.value(this.subjectId, "subjectId", 'must not be blank');
    }
  }

  final FollowSubjectKind subjectType;
  final String subjectId;

  Map<String, Object?> toJson() => <String, Object?>{
    "subjectType": switch (this.subjectType) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", },
    "subjectId": this.subjectId,
  };
}

CloudOperationRequestPayload encodeUserSubjectFollowFollowSubjectGeneratedRequest(FollowSubjectCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subjectType": (switch (request.subjectType) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", }).toString(),
      "subjectId": request.subjectId,
    },
    body: <String, Object?>{
      if (request.source != null) "source": request.source!,
    },
  );
}

CloudOperationRequestPayload encodeUserSubjectFollowUnfollowSubjectGeneratedRequest(UnfollowSubjectCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subjectType": (switch (request.subjectType) { FollowSubjectKind.persona => "persona", FollowSubjectKind.homepage => "homepage", FollowSubjectKind.circle => "circle", FollowSubjectKind.location => "location", }).toString(),
      "subjectId": request.subjectId,
    },
  );
}

