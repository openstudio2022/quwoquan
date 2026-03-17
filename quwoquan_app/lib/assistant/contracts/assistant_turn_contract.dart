export 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
export 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';
import 'package:quwoquan_app/assistant/reasoning/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/reasoning/contracts/process_protocol.dart';
import 'package:quwoquan_app/assistant/reasoning/contracts/run_artifacts.dart';

const String kAssistantTurnCurrentVersion = 'assistant_turn';

AssistantNextAction parseNextAction(String value) =>
    parseAssistantNextAction(value);

AssistantMessageKind parseMessageKind(String value) =>
    parseAssistantMessageKind(value);

AssistantTurnOutput? tryParseAssistantTurnOutput(Map<String, dynamic> json) {
  final version = (json['contractVersion'] as String?)?.trim() ?? '';
  if (version != kAssistantTurnCurrentVersion) return null;
  if (json['decision'] is! Map) return null;
  try {
    final compatJson = <String, dynamic>{...json};
    if (compatJson['uiProcessTimeline'] == null &&
        compatJson['uiProcessTimelineV2'] is List) {
      compatJson['uiProcessTimeline'] = compatJson['uiProcessTimelineV2'];
    }
    final normalizedMessageKind = _normalizeCompatMessageKind(compatJson);
    if (normalizedMessageKind.isEmpty) return null;
    compatJson['messageKind'] = normalizedMessageKind;
    return AssistantTurnOutput.fromJson(compatJson);
  } catch (_) {
    return null;
  }
}

String _normalizeCompatMessageKind(Map<String, dynamic> json) {
  final raw = (json['messageKind'] as String?)?.trim() ?? '';
  if (raw.isNotEmpty) {
    if (parseMessageKind(raw) == AssistantMessageKind.progress &&
        _looksLikeAnswerPhaseTurn(json)) {
      return AssistantMessageKind.answer.wireName;
    }
    return raw;
  }
  final decision =
      (json['decision'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final nextAction = parseNextAction(
    (decision['nextAction'] as String?)?.trim() ?? '',
  );
  switch (nextAction) {
    case AssistantNextAction.toolCall:
      return AssistantMessageKind.progress.wireName;
    case AssistantNextAction.askUser:
      return AssistantMessageKind.askUser.wireName;
    case AssistantNextAction.answer:
      return _hasRenderableAnswerCandidate(json)
          ? AssistantMessageKind.answer.wireName
          : '';
    case AssistantNextAction.abort:
      return AssistantMessageKind.fallback.wireName;
    case AssistantNextAction.retry:
      return AssistantMessageKind.progress.wireName;
    case AssistantNextAction.unknown:
      return '';
  }
}

bool _looksLikeAnswerPhaseTurn(Map<String, dynamic> json) {
  final decision =
      (json['decision'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final nextAction = parseNextAction(
    (decision['nextAction'] as String?)?.trim() ?? '',
  );
  if (nextAction != AssistantNextAction.answer) return false;
  if (!_hasRenderableAnswerCandidate(json)) return false;
  final phaseId = (json['phaseId'] as String?)?.trim() ?? '';
  final actionCode = (json['actionCode'] as String?)?.trim() ?? '';
  final reasonCode = (json['reasonCode'] as String?)?.trim() ?? '';
  return phaseId == PlannerPhaseId.answering.wireName ||
      actionCode == PlannerActionCode.composeAnswer.wireName ||
      reasonCode == PlannerReasonCode.evidenceReady.wireName;
}

bool _hasRenderableAnswerCandidate(Map<String, dynamic> json) {
  final userMarkdown = (json['userMarkdown'] as String?)?.trim() ?? '';
  if (userMarkdown.isNotEmpty) return true;
  final result = (json['result'] as Map?)?.cast<String, dynamic>();
  final resultText = (result?['text'] as String?)?.trim() ?? '';
  if (resultText.isNotEmpty) return true;
  final resultSummary = (result?['summary'] as String?)?.trim() ?? '';
  return resultSummary.isNotEmpty;
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
