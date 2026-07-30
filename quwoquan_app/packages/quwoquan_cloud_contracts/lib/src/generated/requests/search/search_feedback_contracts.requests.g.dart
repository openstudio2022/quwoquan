// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../search/search_feedback_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class ReportSearchFeedbackCommand {
  ReportSearchFeedbackCommand({
    required String searchRequestId,
    required SearchFeedbackEventType eventType,
    String? objectId,
    String? target,
    int? rankPosition,
    String? referralSource,
    String? feedRequestId,
    int? dwellMs,
  }) : searchRequestId = searchRequestId.trim(),
       eventType = eventType,
       objectId = _normalizeGeneratedOptionalText(objectId),
       target = _normalizeGeneratedOptionalText(target),
       rankPosition = rankPosition,
       referralSource = _normalizeGeneratedOptionalText(referralSource),
       feedRequestId = _normalizeGeneratedOptionalText(feedRequestId),
       dwellMs = dwellMs {
    if (this.searchRequestId.isEmpty) {
      throw ArgumentError.value(this.searchRequestId, "searchRequestId", 'must not be blank');
    }
    if (this.dwellMs != null && this.dwellMs! <= 0) {
      throw ArgumentError.value(this.dwellMs, "dwellMs", "must be positive");
    }
    if (this.eventType == SearchFeedbackEventType.dwell && this.dwellMs == null) {
      throw ArgumentError.value(this.dwellMs, "dwellMs", "is required when eventType is dwell");
    }
    if (this.eventType != SearchFeedbackEventType.dwell && this.dwellMs != null) {
      throw ArgumentError.value(this.dwellMs, "dwellMs", "is forbidden unless eventType is dwell");
    }
  }

  final String searchRequestId;
  final SearchFeedbackEventType eventType;
  final String? objectId;
  final String? target;
  final int? rankPosition;
  final String? referralSource;
  final String? feedRequestId;
  final int? dwellMs;
}

CloudOperationRequestPayload encodeSearchFeedbackFactReportSearchFeedbackGeneratedRequest(ReportSearchFeedbackCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "searchRequestId": request.searchRequestId,
      "eventType": switch (request.eventType) { SearchFeedbackEventType.impression => "impression", SearchFeedbackEventType.click => "click", SearchFeedbackEventType.dwell => "dwell", SearchFeedbackEventType.refine => "refine", SearchFeedbackEventType.zeroResult => "zero_result", SearchFeedbackEventType.degrade => "degrade", },
      if (request.objectId != null) "objectId": request.objectId!,
      if (request.target != null) "target": request.target!,
      if (request.rankPosition != null) "rankPosition": request.rankPosition!,
      if (request.referralSource != null) "referralSource": request.referralSource!,
      if (request.feedRequestId != null) "feedRequestId": request.feedRequestId!,
      if (request.dwellMs != null) "dwellMs": request.dwellMs!,
    },
  );
}

