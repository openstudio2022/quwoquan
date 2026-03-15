export 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';
export 'package:quwoquan_app/assistant/internal_legacy/contracts/runtime_enums.dart';

import 'package:quwoquan_app/assistant/internal_legacy/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/internal_legacy/contracts/process_protocol.dart';
import 'package:quwoquan_app/assistant/internal_legacy/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/internal_legacy/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

const String kAssistantTurnCurrentVersion = 'assistant_turn';

AssistantNextAction parseNextAction(String value) =>
    parseAssistantNextAction(value);

AssistantMessageKind parseMessageKind(String value) =>
    parseAssistantMessageKind(value);

AssistantTurnOutput? tryParseAssistantTurnOutput(Map<String, dynamic> json) {
  final version = (json['contractVersion'] as String?)?.trim() ?? '';
  if (version != kAssistantTurnCurrentVersion) return null;
  if (json['decision'] is! Map) return null;
  if ((json['messageKind'] as String?)?.trim().isEmpty ?? true) return null;
  try {
    return AssistantTurnOutput.fromJson(json);
  } catch (_) {
    return null;
  }
}

extension AssistantTurnOutputCompat on AssistantTurnOutput {
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
        (structured['decisionJson'] as Map?)?.cast<String, dynamic>() ??
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
