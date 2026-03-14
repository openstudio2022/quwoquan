export 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/dialogue_round_script.g.dart';

import 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/dialogue_round_script.g.dart';

class DialogueRoundScript extends DialogueRoundScriptDto {
  const DialogueRoundScript({
    super.domainId = '',
    super.enabled = false,
    super.currentStateId = '',
    super.detectedEvent = '',
    super.suggestedNextStateId = '',
    super.nextStateCandidates = const <String>[],
    super.requiredFieldsForNextState = const <String>[],
    super.totalSubTotalRequired = false,
    super.optionalEnrichment = false,
    super.maxQuestionsPerTurn = 0,
    super.hardFailCodes = const <String>[],
    super.passCriteriaRound = const <String, dynamic>{},
    super.statePromptExcerpt = '',
    super.stateMachineExcerpt = '',
    super.routingCatalogVersion = '',
    super.eventCatalogVersion = '',
  });
}
