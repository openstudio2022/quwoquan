import '../operation_request_payload.dart';

final class AssistantLearningFactAppendCommand {
  AssistantLearningFactAppendCommand({
    required String eventId,
    required this.eventVersion,
    required String factType,
    required String assistantTurnId,
    required String referralSource,
    required String domainId,
    String? triggerMessageId,
    String? eventType,
    String? feedbackType,
    this.feedbackScore,
    List<String> reasonCodes = const <String>[],
    String? actionType,
    String? suggestedActionId,
    this.durationMs,
    String? queryText,
    String? answerText,
    String? feedbackText,
    String? correctionText,
    required this.trainingEligible,
    required this.occurredAt,
  }) : eventId = _required(eventId, 'eventId'),
       factType = _required(factType, 'factType'),
       assistantTurnId = _required(assistantTurnId, 'assistantTurnId'),
       referralSource = _required(referralSource, 'referralSource'),
       domainId = _required(domainId, 'domainId'),
       triggerMessageId = _optional(triggerMessageId),
       eventType = _optional(eventType),
       feedbackType = _optional(feedbackType),
       reasonCodes = _normalizedList(reasonCodes),
       actionType = _optional(actionType),
       suggestedActionId = _optional(suggestedActionId),
       queryText = _optional(queryText),
       answerText = _optional(answerText),
       feedbackText = _optional(feedbackText),
       correctionText = _optional(correctionText) {
    if (eventVersion <= 0) {
      throw ArgumentError.value(
        eventVersion,
        'eventVersion',
        'must be positive',
      );
    }
    if (durationMs case final value? when value < 0) {
      throw ArgumentError.value(value, 'durationMs', 'must not be negative');
    }
  }

  final String eventId;
  final int eventVersion;
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

final class AssistantLearningFactAppendReceipt {
  const AssistantLearningFactAppendReceipt({
    required this.eventId,
    required this.eventVersion,
    required this.accepted,
    required this.deduplicated,
    required this.appendSequence,
    required this.payloadDigest,
    required this.recordedAt,
  });

  final String eventId;
  final int eventVersion;
  final bool accepted;
  final bool deduplicated;
  final int appendSequence;
  final String payloadDigest;
  final DateTime recordedAt;
}

CloudOperationRequestPayload encodeAssistantLearningFactAppendCommand(
  AssistantLearningFactAppendCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'eventId': command.eventId,
      'eventVersion': command.eventVersion,
      'factType': command.factType,
      'assistantTurnId': command.assistantTurnId,
      if (command.triggerMessageId case final value?) 'triggerMessageId': value,
      'referralSource': command.referralSource,
      'domainId': command.domainId,
      if (command.eventType case final value?) 'eventType': value,
      if (command.feedbackType case final value?) 'feedbackType': value,
      if (command.feedbackScore case final value?) 'feedbackScore': value,
      if (command.reasonCodes.isNotEmpty) 'reasonCodes': command.reasonCodes,
      if (command.actionType case final value?) 'actionType': value,
      if (command.suggestedActionId case final value?)
        'suggestedActionId': value,
      if (command.durationMs case final value?) 'durationMs': value,
      if (command.queryText case final value?) 'queryText': value,
      if (command.answerText case final value?) 'answerText': value,
      if (command.feedbackText case final value?) 'feedbackText': value,
      if (command.correctionText case final value?) 'correctionText': value,
      'trainingEligible': command.trainingEligible,
      'occurredAt': command.occurredAt.toUtc().toIso8601String(),
    },
  );
}

AssistantLearningFactAppendReceipt decodeAssistantLearningFactAppendReceipt(
  Object? response,
) {
  final value = _object(response, 'AssistantLearningFactAppendReceipt');
  return AssistantLearningFactAppendReceipt(
    eventId: _requiredField(value, 'eventId'),
    eventVersion: _requiredInt(value, 'eventVersion'),
    accepted: _requiredBool(value, 'accepted'),
    deduplicated: _requiredBool(value, 'deduplicated'),
    appendSequence: _requiredInt(value, 'appendSequence'),
    payloadDigest: _requiredField(value, 'payloadDigest'),
    recordedAt: _requiredTimestamp(value, 'recordedAt'),
  );
}

final class AssistantSkillSubscriptionListQuery {
  AssistantSkillSubscriptionListQuery({this.limit = 20, String? status})
    : status = _optional(status) {
    if (limit <= 0 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be in range [1,100]');
    }
  }

  final int limit;
  final String? status;
}

final class AssistantSkillSubscriptionByIdQuery {
  AssistantSkillSubscriptionByIdQuery({required String subscriptionId})
    : subscriptionId = _required(subscriptionId, 'subscriptionId');

  final String subscriptionId;
}

final class AssistantSkillSubscriptionSearchPlan {
  AssistantSkillSubscriptionSearchPlan({
    String rawText = '',
    List<String> queries = const <String>[],
  }) : rawText = rawText.trim(),
       queries = _normalizedList(queries) {
    if (this.rawText.isEmpty && this.queries.isEmpty) {
      throw ArgumentError('rawText or queries is required');
    }
  }

  final String rawText;
  final List<String> queries;

  Map<String, Object?> toJson() => <String, Object?>{
    'rawText': rawText,
    'queries': queries,
  };
}

final class AssistantSkillSubscriptionTrigger {
  AssistantSkillSubscriptionTrigger({
    String type = 'cron',
    required String cron,
  }) : type = _required(type, 'type'),
       cron = _required(cron, 'cron');

  final String type;
  final String cron;

  Map<String, Object?> toJson() => <String, Object?>{
    'type': type,
    'cron': cron,
  };
}

final class AssistantSkillSubscriptionDestination {
  AssistantSkillSubscriptionDestination({
    required String destinationType,
    String? destinationId,
    this.maxPerDay = 1,
    this.cooldownMinutes = 60,
    String quietHoursPolicy = 'inherit_user_setting',
  }) : destinationType = _required(destinationType, 'destinationType'),
       destinationId = _optional(destinationId),
       quietHoursPolicy = _required(quietHoursPolicy, 'quietHoursPolicy') {
    if (maxPerDay <= 0 || cooldownMinutes < 0) {
      throw ArgumentError(
        'maxPerDay must be positive and cooldownMinutes must not be negative',
      );
    }
  }

  final String destinationType;
  final String? destinationId;
  final int maxPerDay;
  final int cooldownMinutes;
  final String quietHoursPolicy;

  Map<String, Object?> toJson() => <String, Object?>{
    'destinationType': destinationType,
    if (destinationId case final value?) 'destinationId': value,
    'maxPerDay': maxPerDay,
    'cooldownMinutes': cooldownMinutes,
    'quietHoursPolicy': quietHoursPolicy,
  };
}

final class CreateAssistantSkillSubscriptionCommand {
  CreateAssistantSkillSubscriptionCommand({
    required String skillId,
    required String domainId,
    List<String> tagRefs = const <String>[],
    required this.searchQueryPlan,
    required this.trigger,
    required this.destination,
    required String clientRequestId,
  }) : skillId = _required(skillId, 'skillId'),
       domainId = _required(domainId, 'domainId'),
       tagRefs = _normalizedList(tagRefs),
       clientRequestId = _required(clientRequestId, 'clientRequestId');

  final String skillId;
  final String domainId;
  final List<String> tagRefs;
  final AssistantSkillSubscriptionSearchPlan searchQueryPlan;
  final AssistantSkillSubscriptionTrigger trigger;
  final AssistantSkillSubscriptionDestination destination;
  final String clientRequestId;
}

final class UpdateAssistantSkillSubscriptionStatusCommand {
  UpdateAssistantSkillSubscriptionStatusCommand({
    required String subscriptionId,
    required String status,
  }) : subscriptionId = _required(subscriptionId, 'subscriptionId'),
       status = _required(status, 'status');

  final String subscriptionId;
  final String status;
}

final class AssistantSkillSubscriptionOwner {
  const AssistantSkillSubscriptionOwner({
    required this.ownerType,
    required this.ownerId,
  });

  final String ownerType;
  final String ownerId;
}

final class AssistantSkillSubscriptionDeliveryState {
  const AssistantSkillSubscriptionDeliveryState({
    required this.pendingDeliveryId,
    required this.lastAttemptAt,
    required this.lastDeliveredAt,
    required this.nextAttemptAt,
    required this.consecutiveFailures,
    required this.lastErrorCode,
  });

  final String? pendingDeliveryId;
  final DateTime? lastAttemptAt;
  final DateTime? lastDeliveredAt;
  final DateTime? nextAttemptAt;
  final int consecutiveFailures;
  final String? lastErrorCode;
}

final class AssistantSkillSubscriptionProjection {
  const AssistantSkillSubscriptionProjection({
    required this.subscriptionId,
    required this.owner,
    required this.createdByUserId,
    required this.createdByPersonaId,
    required this.skillId,
    required this.domainId,
    required this.tagRefs,
    required this.status,
    required this.searchQueryPlan,
    required this.trigger,
    required this.destination,
    required this.deliveryState,
    required this.createdAt,
    required this.updatedAt,
  });

  final String subscriptionId;
  final AssistantSkillSubscriptionOwner owner;
  final String createdByUserId;
  final String? createdByPersonaId;
  final String skillId;
  final String domainId;
  final List<String> tagRefs;
  final String status;
  final AssistantSkillSubscriptionSearchPlan searchQueryPlan;
  final AssistantSkillSubscriptionTrigger trigger;
  final AssistantSkillSubscriptionDestination destination;
  final AssistantSkillSubscriptionDeliveryState deliveryState;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class AssistantSkillSubscriptionListProjection {
  const AssistantSkillSubscriptionListProjection({required this.items});

  final List<AssistantSkillSubscriptionProjection> items;
}

CloudOperationRequestPayload encodeAssistantSkillSubscriptionListQuery(
  AssistantSkillSubscriptionListQuery query,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      'limit': query.limit.toString(),
      if (query.status case final value?) 'status': value,
    },
  );
}

CloudOperationRequestPayload encodeAssistantSkillSubscriptionByIdQuery(
  AssistantSkillSubscriptionByIdQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'subscriptionId': query.subscriptionId},
  );
}

CloudOperationRequestPayload encodeCreateAssistantSkillSubscriptionCommand(
  CreateAssistantSkillSubscriptionCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'skillId': command.skillId,
      'domainId': command.domainId,
      'tagRefs': command.tagRefs,
      'searchQueryPlan': command.searchQueryPlan.toJson(),
      'trigger': command.trigger.toJson(),
      'destination': command.destination.toJson(),
      'clientRequestId': command.clientRequestId,
    },
  );
}

CloudOperationRequestPayload
encodeUpdateAssistantSkillSubscriptionStatusCommand(
  UpdateAssistantSkillSubscriptionStatusCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'subscriptionId': command.subscriptionId},
    body: <String, Object?>{'status': command.status},
  );
}

AssistantSkillSubscriptionProjection decodeAssistantSkillSubscription(
  Object? response,
) {
  final value = _object(response, 'AssistantSkillSubscription');
  final plan = _object(value['searchQueryPlan'], 'searchQueryPlan');
  final trigger = _object(value['trigger'], 'trigger');
  final destination = _object(value['destination'], 'destination');
  final owner = _object(value['owner'], 'owner');
  final deliveryState = _object(value['deliveryState'], 'deliveryState');
  return AssistantSkillSubscriptionProjection(
    subscriptionId: _requiredField(value, 'subscriptionId'),
    owner: AssistantSkillSubscriptionOwner(
      ownerType: _requiredField(owner, 'ownerType'),
      ownerId: _requiredField(owner, 'ownerId'),
    ),
    createdByUserId: _requiredField(value, 'createdByUserId'),
    createdByPersonaId: _optionalField(value, 'createdByPersonaId'),
    skillId: _requiredField(value, 'skillId'),
    domainId: _requiredField(value, 'domainId'),
    tagRefs: _stringList(value['tagRefs']),
    status: _requiredField(value, 'status'),
    searchQueryPlan: AssistantSkillSubscriptionSearchPlan(
      rawText: _optionalField(plan, 'rawText') ?? '',
      queries: _stringList(plan['queries']),
    ),
    trigger: AssistantSkillSubscriptionTrigger(
      type: _requiredField(trigger, 'type'),
      cron: _requiredField(trigger, 'cron'),
    ),
    destination: AssistantSkillSubscriptionDestination(
      destinationType: _requiredField(destination, 'destinationType'),
      destinationId: _optionalField(destination, 'destinationId'),
      maxPerDay: _requiredInt(destination, 'maxPerDay'),
      cooldownMinutes: _requiredInt(destination, 'cooldownMinutes'),
      quietHoursPolicy: _requiredField(destination, 'quietHoursPolicy'),
    ),
    deliveryState: AssistantSkillSubscriptionDeliveryState(
      pendingDeliveryId: _optionalField(deliveryState, 'pendingDeliveryId'),
      lastAttemptAt: _optionalTimestamp(deliveryState, 'lastAttemptAt'),
      lastDeliveredAt: _optionalTimestamp(deliveryState, 'lastDeliveredAt'),
      nextAttemptAt: _optionalTimestamp(deliveryState, 'nextAttemptAt'),
      consecutiveFailures: _requiredInt(deliveryState, 'consecutiveFailures'),
      lastErrorCode: _optionalField(deliveryState, 'lastErrorCode'),
    ),
    createdAt: _requiredTimestamp(value, 'createdAt'),
    updatedAt: _requiredTimestamp(value, 'updatedAt'),
  );
}

AssistantSkillSubscriptionListProjection decodeAssistantSkillSubscriptionList(
  Object? response,
) {
  final value = _object(response, 'AssistantSkillSubscriptionList');
  final rawItems = value['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'AssistantSkillSubscriptionList.items must be a list',
    );
  }
  return AssistantSkillSubscriptionListProjection(
    items: rawItems
        .map<AssistantSkillSubscriptionProjection>(
          decodeAssistantSkillSubscription,
        )
        .toList(growable: false),
  );
}

Map<String, Object?> _object(Object? value, String name) {
  if (value is! Map) {
    throw FormatException('$name must be an object');
  }
  return value.cast<String, Object?>();
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'required');
  }
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

String _requiredField(Map<String, Object?> value, String field) {
  final raw = value[field];
  if (raw is! String || raw.trim().isEmpty) {
    throw FormatException('$field must be a non-empty string');
  }
  return raw.trim();
}

String? _optionalField(Map<String, Object?> value, String field) {
  final raw = value[field];
  if (raw == null) return null;
  if (raw is! String) {
    throw FormatException('$field must be a string');
  }
  return _optional(raw);
}

int _requiredInt(Map<String, Object?> value, String field) {
  final raw = value[field];
  if (raw is! num) {
    throw FormatException('$field must be a number');
  }
  return raw.toInt();
}

bool _requiredBool(Map<String, Object?> value, String field) {
  final raw = value[field];
  if (raw is! bool) {
    throw FormatException('$field must be a bool');
  }
  return raw;
}

DateTime _requiredTimestamp(Map<String, Object?> value, String field) {
  final raw = _requiredField(value, field);
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

DateTime? _optionalTimestamp(Map<String, Object?> value, String field) {
  final raw = _optionalField(value, field);
  if (raw == null) return null;
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

List<String> _normalizedList(List<String> values) {
  return List<String>.unmodifiable(
    values.map((value) => value.trim()).where((value) => value.isNotEmpty),
  );
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    throw const FormatException('value must be a list');
  }
  return List<String>.unmodifiable(
    value.map((item) {
      if (item is! String || item.trim().isEmpty) {
        throw const FormatException('list item must be a non-empty string');
      }
      return item.trim();
    }),
  );
}
