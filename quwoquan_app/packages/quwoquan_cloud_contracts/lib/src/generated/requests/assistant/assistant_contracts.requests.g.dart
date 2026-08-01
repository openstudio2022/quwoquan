// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../assistant/assistant_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

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

final class AssistantLearningFactAppendCommand {
  AssistantLearningFactAppendCommand({
    required String eventId,
    required String factType,
    required String assistantTurnId,
    String? triggerMessageId,
    required String referralSource,
    required String domainId,
    String? eventType,
    String? feedbackType,
    double? feedbackScore,
    List<String> reasonCodes = const <String>[],
    String? actionType,
    String? suggestedActionId,
    int? durationMs,
    String? queryText,
    String? answerText,
    String? feedbackText,
    String? correctionText,
    required bool trainingEligible,
    required DateTime occurredAt,
  }) : eventId = eventId.trim(),
       factType = factType.trim(),
       assistantTurnId = assistantTurnId.trim(),
       triggerMessageId = _normalizeGeneratedOptionalText(triggerMessageId),
       referralSource = referralSource.trim(),
       domainId = domainId.trim(),
       eventType = _normalizeGeneratedOptionalText(eventType),
       feedbackType = _normalizeGeneratedOptionalText(feedbackType),
       feedbackScore = feedbackScore,
       reasonCodes = _normalizeGeneratedTextList(reasonCodes, deduplicate: true),
       actionType = _normalizeGeneratedOptionalText(actionType),
       suggestedActionId = _normalizeGeneratedOptionalText(suggestedActionId),
       durationMs = durationMs,
       queryText = _normalizeGeneratedOptionalText(queryText),
       answerText = _normalizeGeneratedOptionalText(answerText),
       feedbackText = _normalizeGeneratedOptionalText(feedbackText),
       correctionText = _normalizeGeneratedOptionalText(correctionText),
       trainingEligible = trainingEligible,
       occurredAt = occurredAt {
    if (this.eventId.isEmpty) {
      throw ArgumentError.value(this.eventId, "eventId", 'must not be blank');
    }
    if (this.factType.isEmpty) {
      throw ArgumentError.value(this.factType, "factType", 'must not be blank');
    }
    if (this.assistantTurnId.isEmpty) {
      throw ArgumentError.value(this.assistantTurnId, "assistantTurnId", 'must not be blank');
    }
    if (this.referralSource.isEmpty) {
      throw ArgumentError.value(this.referralSource, "referralSource", 'must not be blank');
    }
    if (this.domainId.isEmpty) {
      throw ArgumentError.value(this.domainId, "domainId", 'must not be blank');
    }
  }

  final String eventId;
  final String factType;
  final String assistantTurnId;
  final String? triggerMessageId;
  final String referralSource;
  final String domainId;
  final String? eventType;
  final String? feedbackType;
  final double? feedbackScore;
  final List<String> reasonCodes;
  final String? actionType;
  final String? suggestedActionId;
  final int? durationMs;
  final String? queryText;
  final String? answerText;
  final String? feedbackText;
  final String? correctionText;
  final bool trainingEligible;
  final DateTime occurredAt;

  Map<String, Object?> toJson() => <String, Object?>{
    "eventId": this.eventId,
    "factType": this.factType,
    "assistantTurnId": this.assistantTurnId,
    if (this.triggerMessageId != null) "triggerMessageId": this.triggerMessageId!,
    "referralSource": this.referralSource,
    "domainId": this.domainId,
    if (this.eventType != null) "eventType": this.eventType!,
    if (this.feedbackType != null) "feedbackType": this.feedbackType!,
    if (this.feedbackScore != null) "feedbackScore": this.feedbackScore!,
    if (this.reasonCodes.isNotEmpty) "reasonCodes": this.reasonCodes.map((value) => value).toList(growable: false),
    if (this.actionType != null) "actionType": this.actionType!,
    if (this.suggestedActionId != null) "suggestedActionId": this.suggestedActionId!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
    if (this.queryText != null) "queryText": this.queryText!,
    if (this.answerText != null) "answerText": this.answerText!,
    if (this.feedbackText != null) "feedbackText": this.feedbackText!,
    if (this.correctionText != null) "correctionText": this.correctionText!,
    "trainingEligible": this.trainingEligible,
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
  };
}

final class AssistantSessionByIdQuery {
  AssistantSessionByIdQuery({
    required String sessionId,
  }) : sessionId = sessionId.trim() {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(this.sessionId, "sessionId", 'must not be blank');
    }
  }

  final String sessionId;

  Map<String, Object?> toJson() => <String, Object?>{
    "sessionId": this.sessionId,
  };
}

final class AssistantSessionListQuery {
  AssistantSessionListQuery({
    int limit = 20,
    String? cursor,
  }) : limit = limit,
       cursor = _normalizeGeneratedOptionalText(cursor) {
  }

  final int limit;
  final String? cursor;

  Map<String, Object?> toJson() => <String, Object?>{
    "limit": this.limit,
    if (this.cursor != null) "cursor": this.cursor!,
  };
}

final class AssistantSkillSubscriptionByIdQuery {
  AssistantSkillSubscriptionByIdQuery({
    required String subscriptionId,
  }) : subscriptionId = subscriptionId.trim() {
    if (this.subscriptionId.isEmpty) {
      throw ArgumentError.value(this.subscriptionId, "subscriptionId", 'must not be blank');
    }
  }

  final String subscriptionId;

  Map<String, Object?> toJson() => <String, Object?>{
    "subscriptionId": this.subscriptionId,
  };
}

final class AssistantSkillSubscriptionListQuery {
  AssistantSkillSubscriptionListQuery({
    int limit = 20,
    String? status,
  }) : limit = limit,
       status = _normalizeGeneratedOptionalText(status) {
  }

  final int limit;
  final String? status;

  Map<String, Object?> toJson() => <String, Object?>{
    "limit": this.limit,
    if (this.status != null) "status": this.status!,
  };
}

final class CreateAssistantSkillSubscriptionCommand {
  CreateAssistantSkillSubscriptionCommand({
    required String skillId,
    required String domainId,
    List<String> tagRefs = const <String>[],
    required AssistantSkillSubscriptionSearchPlan searchQueryPlan,
    required AssistantSkillSubscriptionTrigger trigger,
    required AssistantSkillSubscriptionDestination destination,
    required String clientRequestId,
  }) : skillId = skillId.trim(),
       domainId = domainId.trim(),
       tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: true),
       searchQueryPlan = searchQueryPlan,
       trigger = trigger,
       destination = destination,
       clientRequestId = clientRequestId.trim() {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
    if (this.domainId.isEmpty) {
      throw ArgumentError.value(this.domainId, "domainId", 'must not be blank');
    }
    if (this.clientRequestId.isEmpty) {
      throw ArgumentError.value(this.clientRequestId, "clientRequestId", 'must not be blank');
    }
  }

  final String skillId;
  final String domainId;
  final List<String> tagRefs;
  final AssistantSkillSubscriptionSearchPlan searchQueryPlan;
  final AssistantSkillSubscriptionTrigger trigger;
  final AssistantSkillSubscriptionDestination destination;
  final String clientRequestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "skillId": this.skillId,
    "domainId": this.domainId,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
    "searchQueryPlan": this.searchQueryPlan.toJson(),
    "trigger": this.trigger.toJson(),
    "destination": this.destination.toJson(),
    "clientRequestId": this.clientRequestId,
  };
}

final class ListSkillsQuery {
  ListSkillsQuery({
    int? limit,
  }) : limit = limit {
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final int? limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.limit != null) "limit": this.limit!,
  };
}

final class SkillSubscriptionDestination {
  SkillSubscriptionDestination({
    required String destinationType,
    required String destinationId,
    int? maxPerDay,
    int? cooldownMinutes,
    String? quietHoursPolicy,
  }) : destinationType = destinationType,
       destinationId = destinationId,
       maxPerDay = maxPerDay,
       cooldownMinutes = cooldownMinutes,
       quietHoursPolicy = quietHoursPolicy {
    if (!const <String>{"user", "chat_conversation"}.contains(this.destinationType)) {
      throw ArgumentError.value(this.destinationType, "destinationType", 'unsupported canonical enum value');
    }
  }

  final String destinationType;
  final String destinationId;
  final int? maxPerDay;
  final int? cooldownMinutes;
  final String? quietHoursPolicy;

  Map<String, Object?> toJson() => <String, Object?>{
    "destinationType": this.destinationType,
    "destinationId": this.destinationId,
    if (this.maxPerDay != null) "maxPerDay": this.maxPerDay!,
    if (this.cooldownMinutes != null) "cooldownMinutes": this.cooldownMinutes!,
    if (this.quietHoursPolicy != null) "quietHoursPolicy": this.quietHoursPolicy!,
  };
}

final class SkillSubscriptionSearchQueryPlan {
  SkillSubscriptionSearchQueryPlan({
    required String rawText,
    required List<String> queries,
  }) : rawText = rawText,
       queries = List.unmodifiable(queries) {
  }

  final String rawText;
  final List<String> queries;

  Map<String, Object?> toJson() => <String, Object?>{
    "rawText": this.rawText,
    "queries": this.queries.map((value) => value).toList(growable: false),
  };
}

final class SkillSubscriptionTrigger {
  const SkillSubscriptionTrigger({
    required String type,
    required String cron,
  }) : type = type,
       cron = cron;

  final String type;
  final String cron;

  Map<String, Object?> toJson() => <String, Object?>{
    "type": this.type,
    "cron": this.cron,
  };
}

final class UpdateAssistantSkillSubscriptionStatusCommand {
  UpdateAssistantSkillSubscriptionStatusCommand({
    required String subscriptionId,
    required String status,
  }) : subscriptionId = subscriptionId.trim(),
       status = status.trim() {
    if (this.subscriptionId.isEmpty) {
      throw ArgumentError.value(this.subscriptionId, "subscriptionId", 'must not be blank');
    }
    if (this.status.isEmpty) {
      throw ArgumentError.value(this.status, "status", 'must not be blank');
    }
  }

  final String subscriptionId;
  final String status;

  Map<String, Object?> toJson() => <String, Object?>{
    "subscriptionId": this.subscriptionId,
    "status": this.status,
  };
}

CloudOperationRequestPayload encodeAssistantAssistantLearningFactAppendAssistantLearningFactGeneratedRequest(AssistantLearningFactAppendCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "eventId": request.eventId,
      "factType": request.factType,
      "assistantTurnId": request.assistantTurnId,
      if (request.triggerMessageId != null) "triggerMessageId": request.triggerMessageId!,
      "referralSource": request.referralSource,
      "domainId": request.domainId,
      if (request.eventType != null) "eventType": request.eventType!,
      if (request.feedbackType != null) "feedbackType": request.feedbackType!,
      if (request.feedbackScore != null) "feedbackScore": request.feedbackScore!,
      if (request.reasonCodes.isNotEmpty) "reasonCodes": request.reasonCodes.map((value) => value).toList(growable: false),
      if (request.actionType != null) "actionType": request.actionType!,
      if (request.suggestedActionId != null) "suggestedActionId": request.suggestedActionId!,
      if (request.durationMs != null) "durationMs": request.durationMs!,
      if (request.queryText != null) "queryText": request.queryText!,
      if (request.answerText != null) "answerText": request.answerText!,
      if (request.feedbackText != null) "feedbackText": request.feedbackText!,
      if (request.correctionText != null) "correctionText": request.correctionText!,
      "trainingEligible": request.trainingEligible,
      "occurredAt": request.occurredAt.toUtc().toIso8601String(),
    },
  );
}

CloudOperationRequestPayload encodeAssistantAssistantSessionGetAssistantSessionGeneratedRequest(AssistantSessionByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "sessionId": request.sessionId,
    },
  );
}

CloudOperationRequestPayload encodeAssistantAssistantSessionListAssistantSessionsGeneratedRequest(AssistantSessionListQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeAssistantSkillCatalogListSkillsGeneratedRequest(ListSkillsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload encodeAssistantSkillSubscriptionCreateSkillSubscriptionGeneratedRequest(CreateAssistantSkillSubscriptionCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "skillId": request.skillId,
      "domainId": request.domainId,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
      "searchQueryPlan": request.searchQueryPlan.toJson(),
      "trigger": request.trigger.toJson(),
      "destination": request.destination.toJson(),
      "clientRequestId": request.clientRequestId,
    },
  );
}

CloudOperationRequestPayload encodeAssistantSkillSubscriptionGetSkillSubscriptionGeneratedRequest(AssistantSkillSubscriptionByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subscriptionId": request.subscriptionId,
    },
  );
}

CloudOperationRequestPayload encodeAssistantSkillSubscriptionListSkillSubscriptionsGeneratedRequest(AssistantSkillSubscriptionListQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.status != null) "status": request.status!,
    },
  );
}

CloudOperationRequestPayload encodeAssistantSkillSubscriptionUpdateSkillSubscriptionStatusGeneratedRequest(UpdateAssistantSkillSubscriptionStatusCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subscriptionId": request.subscriptionId,
    },
    body: <String, Object?>{
      "status": request.status,
    },
  );
}

