export 'package:quwoquan_app/assistant/assistant/assistant_run/domain/runtime_enums.dart';
export 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/assistant_journey.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/planner_contracts.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/process_protocol.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/run_artifacts.dart'
    show SlotStateSnapshot;
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

const String kAssistantTurnCurrentContractId = 'assistant_turn';

AssistantNextAction parseNextAction(String value) =>
    parseAssistantNextAction(value);

AssistantMessageKind parseMessageKind(String value) =>
    parseAssistantMessageKind(value);

AssistantTurnOutput? tryParseAssistantTurnOutput(Map<String, dynamic> json) {
  final rawContractId = json['contractId'];
  if (rawContractId is! String) return null;
  final contractId = rawContractId.trim();
  if (contractId != kAssistantTurnCurrentContractId) return null;

  final decision = json['decision'];
  if (decision is! Map) return null;
  final nextAction = decision['nextAction'];
  if (nextAction is! String ||
      parseNextAction(nextAction.trim()) == AssistantNextAction.unknown) {
    return null;
  }

  final rawMessageKind = json['messageKind'];
  if (rawMessageKind is! String) return null;
  final messageKind = rawMessageKind.trim();
  if (messageKind.isEmpty ||
      parseMessageKind(messageKind) == AssistantMessageKind.unknown) {
    return null;
  }

  if (!_isCanonicalAssistantTurnResult(json['result'])) return null;
  if (!_isCanonicalAssistantTurnToolCalls(json['toolCalls'])) return null;
  try {
    return AssistantTurnOutput.fromJson(json);
  } catch (_) {
    return null;
  }
}

bool _isCanonicalAssistantTurnResult(Object? value) {
  if (value is! Map) return false;
  for (final key in const <String>['text', 'summary', 'interpretation']) {
    if (value.containsKey(key) && value[key] is! String) return false;
  }
  final actionHints = value['actionHints'];
  if (actionHints != null &&
      (actionHints is! List || actionHints.any((item) => item is! String))) {
    return false;
  }
  return true;
}

bool _isCanonicalAssistantTurnToolCalls(Object? value) {
  if (value == null) return true;
  if (value is! List) return false;
  for (final item in value) {
    if (item is! Map) return false;
    final toolName = item['toolName'];
    if (toolName is! String || toolName.trim().isEmpty) return false;
    if (item['arguments'] is! Map) return false;
  }
  return true;
}

extension AssistantTurnOutputAccessors on AssistantTurnOutput {
  String get nextAction => decision.nextAction.wireName;

  AssistantNextAction get nextActionType => decision.nextAction;

  AssistantMessageKind get messageKindType => messageKind;

  PlannerPhaseId get phaseIdType => phaseId;

  PlannerActionCode get actionCodeType => actionCode;

  PlannerReasonCode get reasonCodeType => reasonCode;

  ProcessProtocolCode get processProtocolCode => ProcessProtocolCode.fromWire(
    stage: phaseId.wireName,
    phaseId: phaseId.wireName,
    actionCode: actionCode.wireName,
    reasonCode: reasonCode.wireName,
  );

  double get confidence => decision.confidence;

  double get selfScoreValue => modelSelfScore.score;

  Map<String, dynamic> get resultData => result.toJson();

  AssistantJourney get assistantJourney => journey;

  String get resultText => result.text.trim();

  String get interpretation => result.interpretation.trim();

  Map<String, dynamic> get askUserData => askUser.toJson();

  bool get hasAskUser =>
      askUser.slotId.trim().isNotEmpty ||
      askUser.prompt.trim().isNotEmpty ||
      askUser.suggestions.isNotEmpty;

  String get askUserPrompt => askUser.prompt.trim();

  String get askUserSlotId => askUser.slotId.trim();

  bool get hasRenderableAnswer =>
      userMarkdown.trim().isNotEmpty || resultText.isNotEmpty;

  bool get hasJourney =>
      journey.stages.isNotEmpty ||
      journey.entries.isNotEmpty ||
      journey.summary.trim().isNotEmpty;

  SlotStateSnapshot get slotStateSnapshot {
    return slotState;
  }

  List<Map<String, dynamic>> get emergedTags => diagnostics.emergedTags;

  Map<String, dynamic> toEnvelopeMap() => toJson();
}

class AssistantTurnDecision {
  const AssistantTurnDecision({
    required this.nextAction,
    required this.messageKind,
  });

  final AssistantNextAction nextAction;
  final AssistantMessageKind messageKind;

  bool get isAnswerReady =>
      nextAction == AssistantNextAction.answer &&
      messageKind != AssistantMessageKind.progress;

  static AssistantTurnDecision fromAnswerPayload(
    Map<String, dynamic> answerPayload,
  ) {
    final turn = tryParseAssistantTurnOutput(answerPayload);
    final nextActionRaw =
        turn?.nextAction ??
        (((answerPayload['decision'] as Map?)?['nextAction'] as String?)
                ?.trim() ??
            '');
    final messageKindRaw =
        turn?.messageKind.wireName ??
        (answerPayload['messageKind'] as String?)?.trim() ??
        '';
    return AssistantTurnDecision(
      nextAction: parseNextAction(nextActionRaw),
      messageKind: parseMessageKind(messageKindRaw),
    );
  }

  static AssistantTurnDecision fromMaps({
    required Map<String, dynamic> structured,
    Map<String, dynamic> answerPayload = const <String, dynamic>{},
  }) {
    final decisionFromStructured =
        (structured['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final decisionFromPayload =
        (answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextActionRaw =
        (decisionFromStructured['nextAction'] as String?)?.trim().isNotEmpty ==
            true
        ? (decisionFromStructured['nextAction'] as String).trim()
        : (decisionFromPayload['nextAction'] as String?)?.trim() ?? '';
    final messageKindRaw =
        (structured['messageKind'] as String?)?.trim().isNotEmpty == true
        ? (structured['messageKind'] as String).trim()
        : (answerPayload['messageKind'] as String?)?.trim() ?? '';
    return AssistantTurnDecision(
      nextAction: parseNextAction(nextActionRaw),
      messageKind: parseMessageKind(messageKindRaw),
    );
  }
}
