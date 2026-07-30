// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../tag/tag_feedback_contracts.dart';

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
}

CloudOperationRequestPayload encodeTagTagFeedbackReportTagFeedbackGeneratedRequest(ReportTagFeedbackCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "tagRef": request.tagRef,
      "action": switch (request.action) { TagFeedbackAction.click => "click", TagFeedbackAction.ignore => "ignore", TagFeedbackAction.correct => "correct", TagFeedbackAction.dislike => "dislike", },
      if (request.context != null) "context": request.context!,
    },
  );
}

