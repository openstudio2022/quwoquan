enum NextTurnMode {
  answer('answer'),
  continueExecution('continue_execution'),
  askUser('ask_user'),
  blocked('blocked');

  const NextTurnMode(this.wireName);

  final String wireName;
}

NextTurnMode parseNextTurnMode(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'continue_execution':
      return NextTurnMode.continueExecution;
    case 'ask_user':
      return NextTurnMode.askUser;
    case 'blocked':
      return NextTurnMode.blocked;
    default:
      return NextTurnMode.answer;
  }
}

class IntentEntityRef {
  const IntentEntityRef({
    required this.entityType,
    required this.canonicalKey,
    this.displayText = '',
  });

  final String entityType;
  final String canonicalKey;
  final String displayText;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'entityType': entityType,
        'canonicalKey': canonicalKey,
        'displayText': displayText,
      };

  factory IntentEntityRef.fromJson(Map<String, dynamic> json) {
    return IntentEntityRef(
      entityType: (json['entityType'] as String?)?.trim() ?? '',
      canonicalKey: (json['canonicalKey'] as String?)?.trim() ?? '',
      displayText: (json['displayText'] as String?)?.trim() ?? '',
    );
  }
}

class IntentConstraint {
  const IntentConstraint({
    required this.key,
    this.value = '',
  });

  final String key;
  final String value;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'key': key,
        'value': value,
      };

  factory IntentConstraint.fromJson(Map<String, dynamic> json) {
    return IntentConstraint(
      key: (json['key'] as String?)?.trim() ?? '',
      value: (json['value'] as String?)?.trim() ?? '',
    );
  }
}

class IntentNode {
  const IntentNode({
    required this.intentId,
    required this.intentType,
    required this.goal,
    this.entityRefs = const <IntentEntityRef>[],
    this.constraints = const <IntentConstraint>[],
    this.requiresEvidence = false,
  });

  final String intentId;
  final String intentType;
  final String goal;
  final List<IntentEntityRef> entityRefs;
  final List<IntentConstraint> constraints;
  final bool requiresEvidence;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'intentId': intentId,
        'intentType': intentType,
        'goal': goal,
        'entityRefs': entityRefs.map((item) => item.toJson()).toList(growable: false),
        'constraints':
            constraints.map((item) => item.toJson()).toList(growable: false),
        'requiresEvidence': requiresEvidence,
      };

  factory IntentNode.fromJson(Map<String, dynamic> json) {
    return IntentNode(
      intentId: (json['intentId'] as String?)?.trim() ?? '',
      intentType: (json['intentType'] as String?)?.trim() ?? '',
      goal: (json['goal'] as String?)?.trim() ?? '',
      entityRefs: _entityRefList(json['entityRefs']),
      constraints: _constraintList(json['constraints']),
      requiresEvidence: json['requiresEvidence'] == true,
    );
  }
}

class DialogueTransitionDecision {
  const DialogueTransitionDecision({
    this.nextTurnMode = NextTurnMode.answer,
    this.needsClarification = false,
    this.clarificationTargetIntentId = '',
    this.canAnswerPartially = false,
  });

  final NextTurnMode nextTurnMode;
  final bool needsClarification;
  final String clarificationTargetIntentId;
  final bool canAnswerPartially;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'nextTurnMode': nextTurnMode.wireName,
        'needsClarification': needsClarification,
        'clarificationTargetIntentId': clarificationTargetIntentId,
        'canAnswerPartially': canAnswerPartially,
      };

  factory DialogueTransitionDecision.fromJson(Map<String, dynamic> json) {
    return DialogueTransitionDecision(
      nextTurnMode:
          parseNextTurnMode((json['nextTurnMode'] as String?)?.trim() ?? ''),
      needsClarification: json['needsClarification'] == true,
      clarificationTargetIntentId:
          (json['clarificationTargetIntentId'] as String?)?.trim() ?? '',
      canAnswerPartially: json['canAnswerPartially'] == true,
    );
  }
}

class UnderstandingResult {
  const UnderstandingResult({
    this.contractId = 'understanding_result',
    this.intents = const <IntentNode>[],
    this.dialogueTransitionDecision = const DialogueTransitionDecision(),
  });

  final String contractId;
  final List<IntentNode> intents;
  final DialogueTransitionDecision dialogueTransitionDecision;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'contractId': contractId,
        'intents': intents.map((item) => item.toJson()).toList(growable: false),
        'dialogueTransitionDecision': dialogueTransitionDecision.toJson(),
      };

  factory UnderstandingResult.fromJson(Map<String, dynamic> json) {
    return UnderstandingResult(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'understanding_result',
      intents: _intentList(json['intents']),
      dialogueTransitionDecision: json['dialogueTransitionDecision'] is Map
          ? DialogueTransitionDecision.fromJson(
              (json['dialogueTransitionDecision'] as Map)
                  .cast<String, dynamic>(),
            )
          : const DialogueTransitionDecision(),
    );
  }
}

List<IntentEntityRef> _entityRefList(Object? value) {
  if (value is! List) {
    return const <IntentEntityRef>[];
  }
  return value
      .whereType<Map>()
      .map((item) => IntentEntityRef.fromJson(item.cast<String, dynamic>()))
      .where(
        (item) =>
            item.entityType.trim().isNotEmpty &&
            item.canonicalKey.trim().isNotEmpty,
      )
      .toList(growable: false);
}

List<IntentConstraint> _constraintList(Object? value) {
  if (value is! List) {
    return const <IntentConstraint>[];
  }
  return value
      .whereType<Map>()
      .map((item) => IntentConstraint.fromJson(item.cast<String, dynamic>()))
      .where((item) => item.key.trim().isNotEmpty)
      .toList(growable: false);
}

List<IntentNode> _intentList(Object? value) {
  if (value is! List) {
    return const <IntentNode>[];
  }
  return value
      .whereType<Map>()
      .map((item) => IntentNode.fromJson(item.cast<String, dynamic>()))
      .where(
        (item) =>
            item.intentId.trim().isNotEmpty &&
            item.intentType.trim().isNotEmpty &&
            item.goal.trim().isNotEmpty,
      )
      .toList(growable: false);
}
