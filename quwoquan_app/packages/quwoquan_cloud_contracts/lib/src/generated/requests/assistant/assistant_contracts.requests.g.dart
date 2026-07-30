// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

final class AssistantConversationByIdQuery {
  AssistantConversationByIdQuery({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
}

final class AssistantConversationListQuery {
  AssistantConversationListQuery({
    int limit = 20,
    String? cursor,
  }) : limit = limit,
       cursor = _normalizeGeneratedOptionalText(cursor) {
  }

  final int limit;
  final String? cursor;
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
}

CloudOperationRequestPayload encodeAssistantAssistantConversationGetAssistantConversationGeneratedRequest(AssistantConversationByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeAssistantAssistantConversationListAssistantConversationsGeneratedRequest(AssistantConversationListQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
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

