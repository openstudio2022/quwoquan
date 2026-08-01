// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/report_commands.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class CreateContentReportCommand {
  CreateContentReportCommand({
    required String targetId,
    required ContentReportTargetType targetType,
    required ContentReportReason reason,
    String? description,
  }) : targetId = targetId.trim(),
       targetType = targetType,
       reason = reason,
       description = _normalizeGeneratedOptionalText(description) {
    if (this.targetId.isEmpty) {
      throw ArgumentError.value(this.targetId, "targetId", 'must not be blank');
    }
  }

  final String targetId;
  final ContentReportTargetType targetType;
  final ContentReportReason reason;
  final String? description;

  Map<String, Object?> toJson() => <String, Object?>{
    "targetId": this.targetId,
    "targetType": switch (this.targetType) { ContentReportTargetType.post => "post", ContentReportTargetType.comment => "comment", ContentReportTargetType.user => "user", ContentReportTargetType.circle => "circle", ContentReportTargetType.message => "message", },
    "reason": switch (this.reason) { ContentReportReason.spam => "spam", ContentReportReason.harassment => "harassment", ContentReportReason.violence => "violence", ContentReportReason.adult => "adult", ContentReportReason.copyright => "copyright", ContentReportReason.other => "other", },
    if (this.description != null) "description": this.description!,
  };
}

CloudOperationRequestPayload encodeContentReportCreateReportGeneratedRequest(CreateContentReportCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "targetId": request.targetId,
      "targetType": switch (request.targetType) { ContentReportTargetType.post => "post", ContentReportTargetType.comment => "comment", ContentReportTargetType.user => "user", ContentReportTargetType.circle => "circle", ContentReportTargetType.message => "message", },
      "reason": switch (request.reason) { ContentReportReason.spam => "spam", ContentReportReason.harassment => "harassment", ContentReportReason.violence => "violence", ContentReportReason.adult => "adult", ContentReportReason.copyright => "copyright", ContentReportReason.other => "other", },
      if (request.description != null) "description": request.description!,
    },
  );
}

