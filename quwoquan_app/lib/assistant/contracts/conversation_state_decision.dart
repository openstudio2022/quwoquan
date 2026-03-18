export 'package:quwoquan_app/assistant/generated/contracts/conversation_state_decision.g.dart';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/generated/contracts/conversation_state_decision.g.dart';
import 'package:quwoquan_app/assistant/reasoning/contracts/run_artifacts.dart';

class ConversationStateDecision extends ConversationStateDecisionDto {
  const ConversationStateDecision({
    required super.nextAction,
    required super.finalAnswerMode,
    required super.answerEligibility,
    super.slotState = const SlotStateSnapshot(),
    super.missingCriticalSlots = const <String>[],
    super.askUser = const AssistantTurnAskUser(),
    super.qualityGates = const QualityGatesDto(),
    super.finalAnswerReady = false,
  });

  String get nextActionWireName => nextAction.wireName;
  String get finalAnswerModeWireName => finalAnswerMode.wireName;
  String get answerEligibilityWireName => answerEligibility.wireName;

  AssistantNextAction get nextActionType => nextAction;
  FinalAnswerMode get finalAnswerModeType => finalAnswerMode;
  AnswerEligibility get answerEligibilityType => answerEligibility;

  Map<String, dynamic> get askUserData => askUser.toJson();
  Map<String, dynamic> get qualityGatesData => qualityGates.toJson();
  Map<String, dynamic> toDecisionMap() => toJson();
}
