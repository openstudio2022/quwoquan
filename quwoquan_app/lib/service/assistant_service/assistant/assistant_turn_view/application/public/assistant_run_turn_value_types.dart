import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/assistant_turn_contract.dart'
    as internal;

/// AssistantRun 解析与规范化输出时所需的最小 turn 值类型 seam。
typedef AssistantTurnOutput = internal.AssistantTurnOutput;
typedef AssistantTurnResult = internal.AssistantTurnResult;
typedef AssistantNextAction = internal.AssistantNextAction;
typedef AssistantMessageKind = internal.AssistantMessageKind;

AssistantTurnOutput? tryParseAssistantTurnOutput(Map<String, dynamic> json) {
  return internal.tryParseAssistantTurnOutput(json);
}

extension AssistantRunTurnOutputAccessors on AssistantTurnOutput {
  AssistantNextAction get nextActionType => decision.nextAction;

  AssistantMessageKind get messageKindType => messageKind;

  String get resultText => result.text.trim();
}
