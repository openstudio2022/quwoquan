import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/reasoning/contracts/run_artifacts.dart';

class AssistantTurnQualityGates {
  const AssistantTurnQualityGates({
    this.structureSafe = true,
    this.taskSafe = true,
    this.evidenceSafe = true,
    this.renderSafe = true,
  });

  final bool structureSafe;
  final bool taskSafe;
  final bool evidenceSafe;
  final bool renderSafe;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'structureSafe': structureSafe,
    'taskSafe': taskSafe,
    'evidenceSafe': evidenceSafe,
    'renderSafe': renderSafe,
  };
}

/// Canonical runtime decision for a single assistant turn.
///
/// Runtime code derives this object from typed orchestrator/synthesis state or
/// from current execution signals, then passes it through answer gating and
/// persistence.
class AssistantTypedTurnDecision {
  const AssistantTypedTurnDecision({
    required this.nextAction,
    required this.finalAnswerMode,
    required this.answerEligibility,
    this.slotState = const SlotStateSnapshot(),
    this.missingCriticalSlots = const <String>[],
    this.askUser = const AssistantTurnAskUser(),
    this.qualityGates = const AssistantTurnQualityGates(),
    this.finalAnswerReady = false,
  });

  final AssistantNextAction nextAction;
  final FinalAnswerMode finalAnswerMode;
  final AnswerEligibility answerEligibility;
  final SlotStateSnapshot slotState;
  final List<String> missingCriticalSlots;
  final AssistantTurnAskUser askUser;
  final AssistantTurnQualityGates qualityGates;
  final bool finalAnswerReady;

  String get nextActionWireName => nextAction.wireName;
  String get finalAnswerModeWireName => finalAnswerMode.wireName;
  String get answerEligibilityWireName => answerEligibility.wireName;

  AssistantNextAction get nextActionType => nextAction;
  FinalAnswerMode get finalAnswerModeType => finalAnswerMode;
  AnswerEligibility get answerEligibilityType => answerEligibility;

  Map<String, dynamic> get askUserData => askUser.toJson();
  Map<String, dynamic> get qualityGatesData => qualityGates.toJson();

  Map<String, dynamic> toJson() => <String, dynamic>{
    'nextAction': nextAction.wireName,
    'finalAnswerMode': finalAnswerMode.wireName,
    'answerEligibility': answerEligibility.wireName,
    'slotState': slotState.toJson(),
    'missingCriticalSlots': missingCriticalSlots,
    'askUser': askUser.toJson(),
    'qualityGates': qualityGates.toJson(),
    'finalAnswerReady': finalAnswerReady,
  };

  Map<String, dynamic> toDecisionMap() => toJson();

  AssistantTypedTurnDecision copyWith({
    AssistantNextAction? nextAction,
    FinalAnswerMode? finalAnswerMode,
    AnswerEligibility? answerEligibility,
    SlotStateSnapshot? slotState,
    List<String>? missingCriticalSlots,
    AssistantTurnAskUser? askUser,
    AssistantTurnQualityGates? qualityGates,
    bool? finalAnswerReady,
  }) {
    return AssistantTypedTurnDecision(
      nextAction: nextAction ?? this.nextAction,
      finalAnswerMode: finalAnswerMode ?? this.finalAnswerMode,
      answerEligibility: answerEligibility ?? this.answerEligibility,
      slotState: slotState ?? this.slotState,
      missingCriticalSlots: missingCriticalSlots ?? this.missingCriticalSlots,
      askUser: askUser ?? this.askUser,
      qualityGates: qualityGates ?? this.qualityGates,
      finalAnswerReady: finalAnswerReady ?? this.finalAnswerReady,
    );
  }

  static AssistantTypedTurnDecision? fromTypedState({
    required ConversationOrchestratorState orchestratorState,
    required TurnSynthesisState turnSynthesisState,
    SlotStateSnapshot groundedSlotState = const SlotStateSnapshot(),
    bool requireSignal = true,
  }) {
    final directive = !turnSynthesisState.interactionDirective.isIdle
        ? turnSynthesisState.interactionDirective
        : orchestratorState.interactionDirective;
    final hasSignal =
        !directive.isIdle ||
        turnSynthesisState.completedIntentIds.isNotEmpty ||
        turnSynthesisState.remainingIntentIds.isNotEmpty ||
        turnSynthesisState.blockedIntentIds.isNotEmpty ||
        orchestratorState.completedTaskIds.isNotEmpty ||
        orchestratorState.currentBatchTaskIds.isNotEmpty ||
        orchestratorState.pendingTaskBatches.isNotEmpty;
    if (requireSignal && !hasSignal) {
      return null;
    }

    switch (directive.kind) {
      case InteractionDirectiveKind.finalAnswer:
        return AssistantTypedTurnDecision(
          nextAction: AssistantNextAction.answer,
          finalAnswerMode: FinalAnswerMode.full,
          answerEligibility: AnswerEligibility.eligible,
          slotState: groundedSlotState,
          finalAnswerReady: true,
        );
      case InteractionDirectiveKind.partialAnswer:
        return AssistantTypedTurnDecision(
          nextAction: AssistantNextAction.answer,
          finalAnswerMode: FinalAnswerMode.boundedAnswer,
          answerEligibility: AnswerEligibility.eligible,
          slotState: groundedSlotState,
          finalAnswerReady: false,
        );
      case InteractionDirectiveKind.clarify:
        return AssistantTypedTurnDecision(
          nextAction: AssistantNextAction.askUser,
          finalAnswerMode: FinalAnswerMode.blocked,
          answerEligibility: AnswerEligibility.blocked,
          slotState: groundedSlotState,
          askUser: AssistantTurnAskUser(
            slotId: directive.intentId.trim(),
            prompt: directive.message.trim(),
            required: true,
            suggestions: const <String>[],
          ),
          finalAnswerReady: false,
        );
      case InteractionDirectiveKind.requiresUserAction:
        return AssistantTypedTurnDecision(
          nextAction: AssistantNextAction.askUser,
          finalAnswerMode: FinalAnswerMode.blocked,
          answerEligibility: AnswerEligibility.blocked,
          slotState: groundedSlotState,
          askUser: AssistantTurnAskUser(
            slotId: directive.intentId.trim(),
            prompt: directive.message.trim(),
            required: true,
          ),
          finalAnswerReady: false,
        );
      case InteractionDirectiveKind.blocked:
        return AssistantTypedTurnDecision(
          nextAction: AssistantNextAction.abort,
          finalAnswerMode: FinalAnswerMode.blocked,
          answerEligibility: AnswerEligibility.blocked,
          slotState: groundedSlotState,
          finalAnswerReady: false,
        );
      case InteractionDirectiveKind.idle:
        if (turnSynthesisState.completedIntentIds.isNotEmpty &&
            turnSynthesisState.remainingIntentIds.isEmpty &&
            turnSynthesisState.blockedIntentIds.isEmpty) {
          return AssistantTypedTurnDecision(
            nextAction: AssistantNextAction.answer,
            finalAnswerMode: FinalAnswerMode.full,
            answerEligibility: AnswerEligibility.eligible,
            slotState: groundedSlotState,
            finalAnswerReady: true,
          );
        }
        if (turnSynthesisState.remainingIntentIds.isNotEmpty ||
            orchestratorState.currentBatchTaskIds.isNotEmpty ||
            orchestratorState.pendingTaskBatches.isNotEmpty) {
          return AssistantTypedTurnDecision(
            nextAction: AssistantNextAction.toolCall,
            finalAnswerMode: FinalAnswerMode.replan,
            answerEligibility: AnswerEligibility.blocked,
            slotState: groundedSlotState,
            finalAnswerReady: false,
          );
        }
        if (turnSynthesisState.blockedIntentIds.isNotEmpty) {
          return AssistantTypedTurnDecision(
            nextAction: AssistantNextAction.abort,
            finalAnswerMode: FinalAnswerMode.blocked,
            answerEligibility: AnswerEligibility.blocked,
            slotState: groundedSlotState,
            finalAnswerReady: false,
          );
        }
        return null;
    }
  }
}
