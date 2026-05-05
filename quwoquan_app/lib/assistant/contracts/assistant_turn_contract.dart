export 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
export 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/process_protocol.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart'
    show SlotStateSnapshot;
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

const String kAssistantTurnCurrentContractId = 'assistant_turn';

AssistantNextAction parseNextAction(String value) =>
    parseAssistantNextAction(value);

AssistantMessageKind parseMessageKind(String value) =>
    parseAssistantMessageKind(value);

AssistantTurnOutput? tryParseAssistantTurnOutput(Map<String, dynamic> json) {
  final contractId = (json['contractId'] as String?)?.trim() ?? '';
  if (contractId != kAssistantTurnCurrentContractId) return null;
  if (json['decision'] is! Map) return null;
  final normalized = _normalizeAssistantTurnJson(json);
  final messageKind = (normalized['messageKind'] as String?)?.trim() ?? '';
  if (messageKind.isEmpty ||
      parseMessageKind(messageKind) == AssistantMessageKind.unknown) {
    return null;
  }
  try {
    return AssistantTurnOutput.fromJson(normalized);
  } catch (_) {
    return null;
  }
}

Map<String, dynamic> _normalizeAssistantTurnJson(Map<String, dynamic> json) {
  final normalized = Map<String, dynamic>.from(json);
  final normalizedToolCalls = _normalizeAssistantTurnToolCalls(normalized);
  if (normalizedToolCalls.isNotEmpty) {
    normalized['toolCalls'] = normalizedToolCalls;
  }
  final resultMap =
      (normalized['result'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final nextAction =
      (((normalized['decision'] as Map?)?.cast<String, dynamic>() ??
                  const <String, dynamic>{})['nextAction']
              as String?)
          ?.trim() ??
      '';
  final currentMessageKind =
      (normalized['messageKind'] as String?)?.trim() ?? '';
  if (currentMessageKind.isEmpty) {
    normalized['messageKind'] = _inferAssistantTurnMessageKind(
      nextAction: nextAction,
      normalizedToolCalls: normalizedToolCalls,
      userMarkdown: (normalized['userMarkdown'] as String?)?.trim() ?? '',
      resultText: (resultMap['text'] as String?)?.trim() ?? '',
    );
  }
  final userMarkdown = (normalized['userMarkdown'] as String?)?.trim() ?? '';
  final resultText = (resultMap['text'] as String?)?.trim() ?? '';
  if (userMarkdown.isEmpty &&
      resultText.isNotEmpty &&
      parseNextAction(nextAction) == AssistantNextAction.answer) {
    normalized['userMarkdown'] = resultText;
  }
  return normalized;
}

List<Map<String, dynamic>> _normalizeAssistantTurnToolCalls(
  Map<String, dynamic> json,
) {
  final primary = json['toolCalls'];
  final rawCalls = primary is List ? primary : const <Object?>[];
  final normalized = <Map<String, dynamic>>[];
  for (final item in rawCalls.whereType<Map>()) {
    final toolName =
        (item['toolName'] as String?)?.trim() ??
        (item['name'] as String?)?.trim() ??
        '';
    if (toolName.isEmpty) continue;
    final rawArguments = item['arguments'];
    final arguments = rawArguments is Map
        ? rawArguments.cast<String, dynamic>()
        : <String, dynamic>{
            for (final entry in item.entries)
              if (entry.key != 'toolName' &&
                  entry.key != 'name' &&
                  entry.key != 'toolCallId' &&
                  entry.key != 'id')
                '${entry.key}': entry.value,
          };
    normalized.add(<String, dynamic>{
      'toolName': toolName,
      'arguments': arguments,
    });
  }
  return normalized;
}

String _inferAssistantTurnMessageKind({
  required String nextAction,
  required List<Map<String, dynamic>> normalizedToolCalls,
  required String userMarkdown,
  required String resultText,
}) {
  final actionType = parseNextAction(nextAction);
  final hasRenderableAnswer =
      userMarkdown.trim().isNotEmpty || resultText.trim().isNotEmpty;
  switch (actionType) {
    case AssistantNextAction.toolCall:
      return AssistantMessageKind.progress.wireName;
    case AssistantNextAction.askUser:
      return AssistantMessageKind.askUser.wireName;
    case AssistantNextAction.answer:
      return hasRenderableAnswer
          ? AssistantMessageKind.answer.wireName
          : AssistantMessageKind.fallback.wireName;
    case AssistantNextAction.retry:
    case AssistantNextAction.replan:
      return AssistantMessageKind.progress.wireName;
    case AssistantNextAction.abort:
      return AssistantMessageKind.fallback.wireName;
    case AssistantNextAction.unknown:
      if (normalizedToolCalls.isNotEmpty) {
        return AssistantMessageKind.progress.wireName;
      }
      if (hasRenderableAnswer) {
        return AssistantMessageKind.answer.wireName;
      }
      return AssistantMessageKind.progress.wireName;
  }
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
