enum InteractionDirectiveKind {
  idle('idle'),
  clarify('clarify'),
  partialAnswer('partial_answer'),
  finalAnswer('final_answer'),
  requiresUserAction('requires_user_action'),
  blocked('blocked');

  const InteractionDirectiveKind(this.wireName);

  final String wireName;
}

InteractionDirectiveKind parseInteractionDirectiveKind(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'partial_answer':
      return InteractionDirectiveKind.partialAnswer;
    case 'clarify':
    case 'clarification':
      return InteractionDirectiveKind.clarify;
    case 'final_answer':
      return InteractionDirectiveKind.finalAnswer;
    case 'requires_user_action':
      return InteractionDirectiveKind.requiresUserAction;
    case 'blocked':
      return InteractionDirectiveKind.blocked;
    default:
      return InteractionDirectiveKind.idle;
  }
}

class InteractionDirective {
  const InteractionDirective({
    this.kind = InteractionDirectiveKind.idle,
    this.intentId = '',
    this.message = '',
  });

  final InteractionDirectiveKind kind;
  final String intentId;
  final String message;

  bool get isIdle =>
      kind == InteractionDirectiveKind.idle &&
      intentId.trim().isEmpty &&
      message.trim().isEmpty;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'kind': kind.wireName,
    'intentId': intentId,
    'message': message,
  };

  factory InteractionDirective.fromJson(Object? raw) {
    if (raw is! Map) {
      return const InteractionDirective();
    }
    final json = raw.cast<String, dynamic>();
    return InteractionDirective(
      kind: parseInteractionDirectiveKind(
        (json['kind'] as String?)?.trim() ?? '',
      ),
      intentId: (json['intentId'] as String?)?.trim() ?? '',
      message: (json['message'] as String?)?.trim() ?? '',
    );
  }
}

class ConversationOrchestratorState {
  const ConversationOrchestratorState({
    this.contractId = 'conversation_orchestrator_state',
    this.completedTaskIds = const <String>[],
    this.currentBatchTaskIds = const <String>[],
    this.pendingTaskBatches = const <List<String>>[],
    this.interactionDirective = const InteractionDirective(),
  });

  final String contractId;
  final List<String> completedTaskIds;
  final List<String> currentBatchTaskIds;
  final List<List<String>> pendingTaskBatches;
  final InteractionDirective interactionDirective;

  ConversationOrchestratorState copyWithInteractionDirective(
    InteractionDirective value,
  ) {
    return ConversationOrchestratorState(
      contractId: contractId,
      completedTaskIds: completedTaskIds,
      currentBatchTaskIds: currentBatchTaskIds,
      pendingTaskBatches: pendingTaskBatches,
      interactionDirective: value,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'completedTaskIds': completedTaskIds,
    'currentBatchTaskIds': currentBatchTaskIds,
    'pendingTaskBatches': pendingTaskBatches,
    'interactionDirective': interactionDirective.toJson(),
  };

  factory ConversationOrchestratorState.fromJson(Map<String, dynamic> json) {
    return ConversationOrchestratorState(
      contractId:
          (json['contractId'] as String?)?.trim() ??
          'conversation_orchestrator_state',
      completedTaskIds: _stringList(json['completedTaskIds']),
      currentBatchTaskIds: _stringList(json['currentBatchTaskIds']),
      pendingTaskBatches: _stringMatrix(json['pendingTaskBatches']),
      interactionDirective: InteractionDirective.fromJson(
        json['interactionDirective'],
      ),
    );
  }
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    return const <String>[];
  }
  return value
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

List<List<String>> _stringMatrix(Object? value) {
  if (value is! List) {
    return const <List<String>>[];
  }
  return value
      .whereType<List>()
      .map<List<String>>(_stringList)
      .where((row) => row.isNotEmpty)
      .toList(growable: false);
}
