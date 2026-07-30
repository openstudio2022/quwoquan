import '../operation_request_payload.dart';
part '../generated/requests/assistant/assistant_contracts.requests.g.dart';

final class AssistantLearningFactAppendReceipt {
  const AssistantLearningFactAppendReceipt({
    required this.eventId,
    required this.accepted,
    required this.deduplicated,
    required this.appendSequence,
    required this.payloadDigest,
    required this.recordedAt,
  });

  final String eventId;
  final bool accepted;
  final bool deduplicated;
  final int appendSequence;
  final String payloadDigest;
  final DateTime recordedAt;
}

AssistantLearningFactAppendReceipt decodeAssistantLearningFactAppendReceipt(
  Object? response,
) {
  final value = _object(response, 'AssistantLearningFactAppendReceipt');
  if (value.containsKey('eventVersion')) {
    throw const FormatException(
      'AssistantLearningFactAppendReceipt.eventVersion is retired',
    );
  }
  return AssistantLearningFactAppendReceipt(
    eventId: _requiredField(value, 'eventId'),
    accepted: _requiredBool(value, 'accepted'),
    deduplicated: _requiredBool(value, 'deduplicated'),
    appendSequence: _requiredInt(value, 'appendSequence'),
    payloadDigest: _requiredSha256Digest(value, 'payloadDigest'),
    recordedAt: _requiredTimestamp(value, 'recordedAt'),
  );
}

/// AssistantConversation 的纯 Dart client projection。
///
/// 字段逐项对应 `assistant_conversation/fields.yaml`；ID、状态与时间戳采用
/// fail-closed 解码，允许领域合同明确允许为空的 turn ID 与 summary 保持空串。
final class AssistantConversationProjection {
  const AssistantConversationProjection({
    required this.conversationId,
    required this.userId,
    required this.state,
    required this.activeTurnId,
    required this.lastTurnId,
    required this.summary,
    required this.createdAt,
    required this.updatedAt,
  });

  final String conversationId;
  final String userId;
  final String state;
  final String activeTurnId;
  final String lastTurnId;
  final String summary;
  final DateTime createdAt;
  final DateTime updatedAt;
}

/// AssistantConversation owner keyset page；`nextCursor == null` 表示末页。
final class AssistantConversationListProjection {
  const AssistantConversationListProjection({
    required this.items,
    required this.nextCursor,
  });

  final List<AssistantConversationProjection> items;
  final String? nextCursor;
}

AssistantConversationProjection decodeAssistantConversation(Object? response) {
  final value = _object(response, 'AssistantConversation');
  return AssistantConversationProjection(
    conversationId: _requiredField(value, 'conversationId'),
    userId: _requiredField(value, 'userId'),
    state: _requiredField(value, 'state'),
    activeTurnId: _stringField(value, 'activeTurnId'),
    lastTurnId: _stringField(value, 'lastTurnId'),
    summary: _stringField(value, 'summary'),
    createdAt: _requiredTimestamp(value, 'createdAt'),
    updatedAt: _requiredTimestamp(value, 'updatedAt'),
  );
}

AssistantConversationListProjection decodeAssistantConversationList(
  Object? response,
) {
  final value = _object(response, 'AssistantConversationList');
  final rawItems = value['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'AssistantConversationList.items must be a list',
    );
  }
  return AssistantConversationListProjection(
    items: rawItems
        .map<AssistantConversationProjection>(decodeAssistantConversation)
        .toList(growable: false),
    nextCursor: _optionalField(value, 'nextCursor'),
  );
}

/// SkillCatalog 的严格 client projection；仅承载 canonical 私有响应字段。
final class AssistantSkillCatalogItemProjection {
  const AssistantSkillCatalogItemProjection({
    required this.skillId,
    required this.displayName,
    this.description,
    this.category,
    required this.requiresConsent,
    this.iconHint,
  });

  final String skillId;
  final String displayName;
  final String? description;
  final String? category;
  final bool requiresConsent;
  final String? iconHint;
}

final class AssistantSkillCatalogListProjection {
  const AssistantSkillCatalogListProjection({required this.items});

  final List<AssistantSkillCatalogItemProjection> items;
}

AssistantSkillCatalogListProjection decodeAssistantSkillCatalogList(
  Object? response,
) {
  final value = _object(response, 'AssistantSkillCatalogListView');
  final rawItems = value['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'AssistantSkillCatalogListView.items must be a list',
    );
  }
  return AssistantSkillCatalogListProjection(
    items: rawItems
        .map((raw) {
          final item = _object(raw, 'AssistantSkillCatalogItemView');
          return AssistantSkillCatalogItemProjection(
            skillId: _requiredField(item, 'skillId'),
            displayName: _requiredField(item, 'displayName'),
            description: _optionalField(item, 'description'),
            category: _optionalField(item, 'category'),
            requiresConsent: _requiredBool(item, 'requiresConsent'),
            iconHint: _optionalField(item, 'iconHint'),
          );
        })
        .toList(growable: false),
  );
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

String _stringField(Map<String, Object?> value, String field) {
  final raw = value[field];
  if (raw is! String) {
    throw FormatException('$field must be a string');
  }
  return raw.trim();
}

int _requiredInt(Map<String, Object?> value, String field) {
  final raw = value[field];
  if (raw is! num) {
    throw FormatException('$field must be a number');
  }
  return raw.toInt();
}

String _requiredSha256Digest(Map<String, Object?> value, String field) {
  final digest = _requiredField(value, field);
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(digest)) {
    throw FormatException('$field must be a lowercase SHA-256 digest');
  }
  return digest;
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
