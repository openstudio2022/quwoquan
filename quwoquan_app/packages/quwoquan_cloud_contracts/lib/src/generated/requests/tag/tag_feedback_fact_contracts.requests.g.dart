// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../tag/tag_feedback_fact_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class ReportTagFeedbackCommand {
  ReportTagFeedbackCommand({
    required String tagRef,
    required TagFeedbackAction action,
    String? context,
  }) : tagRef = tagRef.trim(),
       action = action,
       context = _normalizeGeneratedOptionalText(context) {
    if (this.tagRef.isEmpty) {
      throw ArgumentError.value(this.tagRef, "tagRef", 'must not be blank');
    }
  }

  final String tagRef;
  final TagFeedbackAction action;
  final String? context;

  Map<String, Object?> toJson() => <String, Object?>{
    "tagRef": this.tagRef,
    "action": switch (this.action) { TagFeedbackAction.click => "click", TagFeedbackAction.ignore => "ignore", TagFeedbackAction.correct => "correct", TagFeedbackAction.dislike => "dislike", },
    if (this.context != null) "context": this.context!,
  };
}

CloudOperationRequestPayload encodeTagTagFeedbackFactReportTagFeedbackGeneratedRequest(ReportTagFeedbackCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "tagRef": request.tagRef,
      "action": switch (request.action) { TagFeedbackAction.click => "click", TagFeedbackAction.ignore => "ignore", TagFeedbackAction.correct => "correct", TagFeedbackAction.dislike => "dislike", },
      if (request.context != null) "context": request.context!,
    },
  );
}

