import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/slot_schema.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/default_processing_copy_bank.dart';

class ConversationStateKernel {
  const ConversationStateKernel();

  SlotSchema defaultSlotSchema({
    required String domainId,
    required String problemClass,
    required DialogueRoundScript dialogueRoundScript,
  }) {
    final requiredSlots = <String>[
      ...dialogueRoundScript.requiredFieldsForNextState,
    ];
    final problemClassKind = parseProblemClass(problemClass);
    final optionalSlots = <String>[];
    if (problemClassKind == ProblemClass.realtimeInfo) {
      optionalSlots.addAll(const <String>['timeScope', 'date']);
    }
    if (problemClassKind == ProblemClass.complexReasoning) {
      optionalSlots.addAll(const <String>['budget', 'constraints', 'audience']);
    }
    return SlotSchema(
      requiredSlots: requiredSlots.toList(growable: false),
      optionalSlots: optionalSlots
          .where((slotId) => !requiredSlots.contains(slotId))
          .toSet()
          .toList(growable: false),
      carryOver: true,
      stateId: dialogueRoundScript.currentStateId,
      nextStateId: dialogueRoundScript.suggestedNextStateId,
    );
  }

  ConversationStateDecision evaluate({
    required String domainId,
    required String problemClass,
    required IntentGraph intentGraph,
    required List<QueryTask> queryTasks,
    required DialogueRoundScript dialogueRoundScript,
    required AggregationState aggregationState,
    required Map<String, dynamic> answerPayload,
    required SlotStateSnapshot previousSlotState,
    required EvidenceEvaluationResult evidenceEvaluation,
    required SlotSchema slotSchema,
  }) {
    final parsedTurn = tryParseAssistantTurnOutput(answerPayload);
    final requiredSlots = slotSchema.requiredSlots;
    final mergedSlots = <String, SlotValueSnapshot>{
      ...previousSlotState.slotValues,
    };
    final slotFillPlan = SlotFillPlan.fromJson(
      (answerPayload['slotFillPlan'] as Map?)?.cast<String, dynamic>(),
    );
    final contextSlots =
        (answerPayload['contextSlots'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final plannerSlots = <String, dynamic>{
      ...contextSlots,
      ...slotFillPlan.toFilledSlots(),
    };
    if (plannerSlots.isNotEmpty) {
      for (final entry in plannerSlots.entries) {
        final slotId = entry.key.trim();
        if (slotId.isEmpty) continue;
        final sfEntry = slotFillPlan.entries[slotId];
        _mergeSlot(
          mergedSlots,
          SlotValueSnapshot(
            slotId: slotId,
            status: SlotValueStatus.inferred,
            value: entry.value,
            source:
                sfEntry?.source.wireName ?? SlotSource.userQueryLlm.wireName,
            confidence: sfEntry?.confidence ?? 0.85,
          ),
        );
      }
    }
    for (final entry
        in parsedTurn?.slotStateSnapshot.slotValues.entries ??
            const Iterable<MapEntry<String, SlotValueSnapshot>>.empty()) {
      final slotId = entry.key.trim();
      if (slotId.isEmpty) continue;
      final snapshot = entry.value.slotId.trim().isNotEmpty
          ? entry.value
          : SlotValueSnapshot(
              slotId: slotId,
              status: entry.value.status,
              value: entry.value.value,
              source: entry.value.source,
              confidence: entry.value.confidence,
              candidates: entry.value.candidates,
              evidenceIds: entry.value.evidenceIds,
            );
      _mergeSlot(mergedSlots, snapshot);
    }
    final rawPayloadSlots = parsedTurn == null
        ? ((answerPayload['slotState'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{})
        : const <String, dynamic>{};
    final payloadSlots =
        (rawPayloadSlots['slotValues'] as Map?)?.cast<String, dynamic>() ??
        rawPayloadSlots;
    for (final entry in payloadSlots.entries) {
      final normalized = _normalizePayloadSlot(entry.key, entry.value);
      _mergeSlot(mergedSlots, normalized);
    }
    final unnamedSlot = mergedSlots[''];
    if (unnamedSlot != null) {
      final fallbackSlotId = requiredSlots.firstWhere(
        (item) =>
            item.trim().isNotEmpty && !mergedSlots.containsKey(item.trim()),
        orElse: () => '',
      );
      if (fallbackSlotId.isNotEmpty) {
        mergedSlots.remove('');
        mergedSlots[fallbackSlotId] = unnamedSlot.copyWith(
          slotId: fallbackSlotId,
        );
      }
    }
    final missingHints = <String>{
      ...((answerPayload['missingContextSlots'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty) ??
          const Iterable<String>.empty()),
      ...requiredSlots,
    };
    for (final slotId in missingHints) {
      final current = mergedSlots[slotId];
      if (current == null || !_hasUsableValue(current)) {
        mergedSlots[slotId] = SlotValueSnapshot(
          slotId: slotId,
          status: SlotValueStatus.missing,
          source: current?.source ?? '',
          value: current?.value,
          confidence: current?.confidence ?? 0,
          candidates: current?.candidates ?? const <String>[],
          evidenceIds: current?.evidenceIds ?? const <String>[],
        );
      }
    }
    final missingCriticalSlots = requiredSlots
        .where((slotId) => !_hasUsableValue(mergedSlots[slotId]))
        .toList(growable: false);
    final turnDecision = AssistantTurnDecision.fromAnswerPayload(answerPayload);
    final rawAskUser =
        (answerPayload['askUser'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final explicitAskUserPayload = AssistantTurnAskUser.fromJson(rawAskUser);
    final explicitAskUser =
        turnDecision.nextAction == AssistantNextAction.askUser ||
        turnDecision.messageKind == AssistantMessageKind.askUser ||
        (parsedTurn?.hasAskUser ?? false) ||
        explicitAskUserPayload.slotId.trim().isNotEmpty ||
        explicitAskUserPayload.prompt.trim().isNotEmpty ||
        explicitAskUserPayload.suggestions.isNotEmpty;
    final evidenceStatusType =
        evidenceEvaluation.status != EvidenceStatus.unknown
        ? evidenceEvaluation.status
        : (evidenceEvaluation.passed
              ? EvidenceStatus.full
              : EvidenceStatus.retry);
    final requiresEvidenceContinuation =
        evidenceEvaluation.evidenceRequired ||
        queryTasks.isNotEmpty ||
        intentGraph.requiresExternalEvidence ||
        intentGraph.mustVerifyClaims;
    final hasGroundingEvidence =
        evidenceEvaluation.entries.isNotEmpty ||
        aggregationState.canGivePartialAnswer ||
        !requiresEvidenceContinuation;
    final modelNextAction = turnDecision.nextAction;
    final resultInterpretation =
        (answerPayload['result'] as Map?)?['interpretation']
            ?.toString()
            .trim()
            .toLowerCase() ??
        '';
    final explicitBlockedPayload =
        modelNextAction == AssistantNextAction.abort ||
        turnDecision.messageKind == AssistantMessageKind.fallback ||
        resultInterpretation == 'fallback' ||
        resultInterpretation == 'retrieval_processing_blocked';
    late final AssistantNextAction nextActionType;
    late final FinalAnswerMode finalAnswerModeType;
    if (missingCriticalSlots.isNotEmpty ||
        explicitAskUser ||
        modelNextAction == AssistantNextAction.askUser) {
      nextActionType = AssistantNextAction.askUser;
      finalAnswerModeType = FinalAnswerMode.clarify;
    } else if (modelNextAction == AssistantNextAction.toolCall) {
      nextActionType = AssistantNextAction.toolCall;
      finalAnswerModeType = FinalAnswerMode.replan;
    } else if (modelNextAction == AssistantNextAction.replan) {
      nextActionType = AssistantNextAction.toolCall;
      finalAnswerModeType = FinalAnswerMode.replan;
    } else if (explicitBlockedPayload) {
      if (aggregationState.needExpansion || requiresEvidenceContinuation) {
        nextActionType = AssistantNextAction.toolCall;
        finalAnswerModeType = FinalAnswerMode.replan;
      } else {
        nextActionType = AssistantNextAction.abort;
        finalAnswerModeType = FinalAnswerMode.blocked;
      }
    } else if (modelNextAction == AssistantNextAction.answer) {
      final shouldPreferReplan =
          !evidenceEvaluation.passed &&
          (aggregationState.needExpansion ||
              evidenceStatusType == EvidenceStatus.retry ||
              (!hasGroundingEvidence && requiresEvidenceContinuation) ||
              (requiresEvidenceContinuation &&
                  !aggregationState.canGivePartialAnswer &&
                  evidenceStatusType != EvidenceStatus.bounded));
      if (shouldPreferReplan) {
        nextActionType = AssistantNextAction.toolCall;
        finalAnswerModeType = FinalAnswerMode.replan;
      } else {
        nextActionType = AssistantNextAction.answer;
        finalAnswerModeType =
            evidenceStatusType == EvidenceStatus.full ||
                evidenceStatusType == EvidenceStatus.notRequired
            ? FinalAnswerMode.full
            : FinalAnswerMode.boundedAnswer;
      }
    } else if (evidenceStatusType == EvidenceStatus.full ||
        evidenceStatusType == EvidenceStatus.notRequired) {
      nextActionType = AssistantNextAction.answer;
      finalAnswerModeType = FinalAnswerMode.full;
    } else if (evidenceStatusType == EvidenceStatus.bounded) {
      if (hasGroundingEvidence) {
        nextActionType = AssistantNextAction.answer;
        finalAnswerModeType = FinalAnswerMode.boundedAnswer;
      } else {
        nextActionType = AssistantNextAction.toolCall;
        finalAnswerModeType = FinalAnswerMode.replan;
      }
    } else if (!evidenceEvaluation.passed) {
      final shouldPreferReplan =
          aggregationState.needExpansion ||
          evidenceStatusType == EvidenceStatus.retry ||
          !hasGroundingEvidence ||
          (requiresEvidenceContinuation &&
              !aggregationState.canGivePartialAnswer &&
              evidenceStatusType != EvidenceStatus.bounded);
      if (shouldPreferReplan) {
        nextActionType = AssistantNextAction.toolCall;
        finalAnswerModeType = FinalAnswerMode.replan;
      } else if (hasGroundingEvidence) {
        nextActionType = AssistantNextAction.answer;
        finalAnswerModeType = FinalAnswerMode.boundedAnswer;
      } else {
        nextActionType = AssistantNextAction.toolCall;
        finalAnswerModeType = FinalAnswerMode.replan;
      }
    } else if (aggregationState.needExpansion &&
        !aggregationState.finalAnswerReady) {
      nextActionType = AssistantNextAction.toolCall;
      finalAnswerModeType = FinalAnswerMode.replan;
    } else {
      nextActionType = AssistantNextAction.answer;
      finalAnswerModeType = FinalAnswerMode.full;
    }
    final askUserMap = (parsedTurn?.hasAskUser ?? false)
        ? parsedTurn!.askUserData
        : (explicitAskUserPayload.slotId.trim().isNotEmpty ||
              explicitAskUserPayload.prompt.trim().isNotEmpty ||
              explicitAskUserPayload.suggestions.isNotEmpty)
        ? rawAskUser
        : <String, dynamic>{
            if (missingCriticalSlots.isNotEmpty)
              AssistantTurnAskUserFields.slotId: missingCriticalSlots.first,
            if (missingCriticalSlots.isNotEmpty)
              AssistantTurnAskUserFields.prompt: _defaultAskUserPrompt(
                slotId: missingCriticalSlots.first,
              ),
          };
    final askUser = AssistantTurnAskUser.fromJson(askUserMap);
    final finalAnswerReady =
        nextActionType == AssistantNextAction.answer &&
        (finalAnswerModeType == FinalAnswerMode.full ||
            finalAnswerModeType == FinalAnswerMode.boundedAnswer);
    final qualityGates = QualityGatesDto(
      structureSafe: true,
      taskSafe:
          missingCriticalSlots.isEmpty ||
          nextActionType == AssistantNextAction.askUser,
      evidenceSafe:
          evidenceEvaluation.passed ||
          evidenceStatusType == EvidenceStatus.bounded,
      renderSafe: finalAnswerModeType != FinalAnswerMode.replan,
    );
    return ConversationStateDecision(
      nextAction: nextActionType,
      finalAnswerMode: finalAnswerModeType,
      answerEligibility: finalAnswerReady
          ? AnswerEligibility.eligible
          : (nextActionType == AssistantNextAction.askUser
                ? AnswerEligibility.clarify
                : AnswerEligibility.blocked),
      slotState: SlotStateSnapshot(
        domainId: domainId,
        slots: const <String, dynamic>{},
        slotValues: mergedSlots,
        missingSlots: missingCriticalSlots,
        updatedAt: DateTime.now().toIso8601String(),
      ),
      missingCriticalSlots: missingCriticalSlots,
      askUser: askUser,
      qualityGates: qualityGates,
      finalAnswerReady: finalAnswerReady,
    );
  }

  SlotValueSnapshot _normalizePayloadSlot(String slotId, Object? raw) {
    if (raw is Map) {
      final typed = raw.cast<String, dynamic>();
      if (typed['status'] != null || typed['value'] != null) {
        return SlotValueSnapshot.fromJson(<String, dynamic>{
          'slotId': slotId,
          ...typed,
        }).copyWith(
          source: (typed['source'] as String?)?.trim().isNotEmpty == true
              ? (typed['source'] as String).trim()
              : 'model',
        );
      }
      return SlotValueSnapshot(
        slotId: slotId,
        status: SlotValueStatus.confirmed,
        value: typed,
        source: 'model',
        confidence: 0.8,
      );
    }
    final value = SlotValueCodec.displayForSlotMerge(raw);
    return SlotValueSnapshot(
      slotId: slotId,
      status: value.isEmpty
          ? SlotValueStatus.missing
          : SlotValueStatus.confirmed,
      value: value.isEmpty ? null : raw,
      source: 'model',
      confidence: value.isEmpty ? 0 : 0.82,
    );
  }

  void _mergeSlot(
    Map<String, SlotValueSnapshot> target,
    SlotValueSnapshot incoming,
  ) {
    final current = target[incoming.slotId];
    if (current == null) {
      target[incoming.slotId] = incoming;
      return;
    }
    final currentValue = current.value?.toString().trim() ?? '';
    final incomingValue = incoming.value?.toString().trim() ?? '';
    if (currentValue.isNotEmpty &&
        incomingValue.isNotEmpty &&
        currentValue != incomingValue) {
      target[incoming.slotId] = SlotValueSnapshot(
        slotId: incoming.slotId,
        status: SlotValueStatus.conflicted,
        value: current.value,
        source: incoming.source.isNotEmpty ? incoming.source : current.source,
        confidence: current.confidence > incoming.confidence
            ? current.confidence
            : incoming.confidence,
        candidates: <String>{
          currentValue,
          incomingValue,
          ...current.candidates,
          ...incoming.candidates,
        }.toList(growable: false),
      );
      return;
    }
    if (!_hasUsableValue(current) && _hasUsableValue(incoming)) {
      target[incoming.slotId] = incoming;
      return;
    }
    if (incoming.status == SlotValueStatus.confirmed &&
        current.status != SlotValueStatus.confirmed) {
      target[incoming.slotId] = incoming;
      return;
    }
    if (currentValue.isEmpty && incomingValue.isNotEmpty) {
      target[incoming.slotId] = incoming;
      return;
    }
    if (incoming.confidence > current.confidence && incomingValue.isNotEmpty) {
      target[incoming.slotId] = incoming;
    }
  }

  bool _hasUsableValue(SlotValueSnapshot? slot) {
    if (slot == null) return false;
    final value = SlotValueCodec.displayForSlotMerge(slot.value);
    if (value.isEmpty) return false;
    return slot.status != SlotValueStatus.missing &&
        slot.status != SlotValueStatus.conflicted;
  }

  String _defaultAskUserPrompt({required String slotId}) {
    return DefaultProcessingCopyBank.conversationKernelAskPrompt(slotId);
  }
}
