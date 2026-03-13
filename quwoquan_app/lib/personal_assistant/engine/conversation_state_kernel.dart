import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/evidence_evaluator.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';
import 'package:quwoquan_app/personal_assistant/engine/dialogue_state_runtime.dart';

class ConversationStateDecision {
  const ConversationStateDecision({
    required this.nextAction,
    required this.finalAnswerMode,
    required this.answerEligibility,
    required this.slotState,
    required this.missingCriticalSlots,
    required this.askUser,
    required this.qualityGates,
    required this.finalAnswerReady,
  });

  final String nextAction;
  final String finalAnswerMode;
  final String answerEligibility;
  final SlotStateSnapshot slotState;
  final List<String> missingCriticalSlots;
  final Map<String, dynamic> askUser;
  final Map<String, dynamic> qualityGates;
  final bool finalAnswerReady;

  Map<String, dynamic> toDecisionMap() => <String, dynamic>{
    'nextAction': nextAction,
    'finalAnswerMode': finalAnswerMode,
    'answerEligibility': answerEligibility,
    'missingCriticalSlots': missingCriticalSlots,
    'qualityGates': qualityGates,
    'finalAnswerReady': finalAnswerReady,
  };
}

class ConversationStateKernel {
  const ConversationStateKernel({
    this.problemFramer = const DefaultProblemFramer(),
  });

  final DefaultProblemFramer problemFramer;

  Map<String, dynamic> defaultSlotSchema({
    required String query,
    required String domainId,
    required String problemClass,
    required DialogueRoundScript dialogueRoundScript,
  }) {
    final frame = problemFramer.frame(query);
    final requiredSlots = <String>[
      ...dialogueRoundScript.requiredFieldsForNextState,
    ];
    final optionalSlots = <String>[];
    if (domainId == 'weather') {
      if (!requiredSlots.contains('city')) requiredSlots.add('city');
      optionalSlots.addAll(const <String>['date', 'weatherMetric']);
    } else if (frame.queryIntent == 'stayPlanning' ||
        (problemClass == 'complex_reasoning' &&
            frame.queryIntent != 'travelAlternativeOptions')) {
      if (!requiredSlots.contains('destination')) {
        requiredSlots.add('destination');
      }
      optionalSlots.addAll(const <String>['budget', 'days', 'companionType']);
    } else if (frame.queryIntent == 'travelAlternativeOptions') {
      optionalSlots.addAll(const <String>[
        'destination',
        'days',
        'companionType',
      ]);
    }
    return <String, dynamic>{
      'requiredSlots': requiredSlots.toList(growable: false),
      'optionalSlots': optionalSlots.toList(growable: false),
      'carryOver': true,
      'stateId': dialogueRoundScript.currentStateId,
      'nextStateId': dialogueRoundScript.suggestedNextStateId,
    };
  }

  ConversationStateDecision evaluate({
    required String query,
    required String domainId,
    required String problemClass,
    required DialogueRoundScript dialogueRoundScript,
    required AggregationState aggregationState,
    required Map<String, dynamic> answerPayload,
    required SlotStateSnapshot previousSlotState,
    required EvidenceEvaluationResult evidenceEvaluation,
    required Map<String, dynamic> slotSchema,
  }) {
    final frame = problemFramer.frame(query);
    final requiredSlots =
        (slotSchema['requiredSlots'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final mergedSlots = <String, SlotValueSnapshot>{
      ...previousSlotState.slotValues,
    };
    final querySlots = _extractSlotsFromQuery(
      query: query,
      domainId: domainId,
      problemClass: problemClass,
    );
    for (final entry in querySlots.entries) {
      _mergeSlot(
        mergedSlots,
        SlotValueSnapshot(
          slotId: entry.key,
          status: SlotValueStatus.inferred,
          value: entry.value,
          source: 'query',
          confidence: 0.72,
        ),
      );
    }
    final payloadSlots =
        (answerPayload['slotState'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    for (final entry in payloadSlots.entries) {
      final normalized = _normalizePayloadSlot(entry.key, entry.value);
      _mergeSlot(mergedSlots, normalized);
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
    final legacySlots = <String, dynamic>{};
    for (final entry in mergedSlots.entries) {
      if (_hasUsableValue(entry.value)) {
        legacySlots[entry.key] = entry.value.value;
      }
    }
    final missingCriticalSlots = requiredSlots
        .where((slotId) => !_hasUsableValue(mergedSlots[slotId]))
        .toList(growable: false);
    final explicitAskUser =
        (((answerPayload['decision'] as Map?)?['nextAction'] as String?)
                    ?.trim() ??
                '') ==
            'ask_user' ||
        ((answerPayload['messageKind'] as String?)?.trim() ?? '') ==
            'ask_user' ||
        ((answerPayload['askUser'] as Map?)?.isNotEmpty ?? false);
    final evidenceStatus = evidenceEvaluation.status.trim().isNotEmpty
        ? evidenceEvaluation.status.trim()
        : (evidenceEvaluation.passed ? 'full' : 'retry');
    late final String nextAction;
    late final String finalAnswerMode;
    if (missingCriticalSlots.isNotEmpty || explicitAskUser) {
      nextAction = 'ask_user';
      finalAnswerMode = 'clarify';
    } else if (evidenceStatus == 'full' || evidenceStatus == 'not_required') {
      nextAction = 'answer';
      finalAnswerMode = 'full';
    } else if (evidenceStatus == 'bounded') {
      nextAction = 'answer';
      finalAnswerMode = 'bounded_answer';
    } else if (!evidenceEvaluation.passed) {
      if (evidenceEvaluation.entries.isNotEmpty ||
          aggregationState.canGivePartialAnswer) {
        nextAction = 'answer';
        finalAnswerMode = 'bounded_answer';
      } else if (aggregationState.needExpansion ||
          problemClass == 'complex_reasoning' ||
          problemClass == 'evidence_lookup' ||
          frame.queryIntent == 'travelAlternativeOptions' ||
          frame.queryIntent == 'wildlifeBestTime') {
        nextAction = 'retry';
        finalAnswerMode = 'retry';
      } else {
        nextAction = 'answer';
        finalAnswerMode = 'bounded_answer';
      }
    } else if (aggregationState.needExpansion &&
        !aggregationState.finalAnswerReady) {
      nextAction = 'retry';
      finalAnswerMode = 'retry';
    } else {
      nextAction = 'answer';
      finalAnswerMode = 'full';
    }
    final askUser =
        (answerPayload['askUser'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{
          if (missingCriticalSlots.isNotEmpty)
            'slotId': missingCriticalSlots.first,
          if (missingCriticalSlots.isNotEmpty)
            'prompt': _defaultAskUserPrompt(
              slotId: missingCriticalSlots.first,
              domainId: domainId,
            ),
        };
    final finalAnswerReady =
        nextAction == 'answer' &&
        (finalAnswerMode == 'full' || finalAnswerMode == 'bounded_answer');
    final qualityGates = <String, dynamic>{
      'structureSafe': true,
      'taskSafe': missingCriticalSlots.isEmpty || nextAction == 'ask_user',
      'evidenceSafe': evidenceEvaluation.passed || evidenceStatus == 'bounded',
      'renderSafe': finalAnswerMode != 'retry',
    };
    return ConversationStateDecision(
      nextAction: nextAction,
      finalAnswerMode: finalAnswerMode,
      answerEligibility: finalAnswerReady
          ? 'eligible'
          : (nextAction == 'ask_user' ? 'clarify' : 'blocked'),
      slotState: SlotStateSnapshot(
        domainId: domainId,
        slots: legacySlots,
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

  Map<String, dynamic> _extractSlotsFromQuery({
    required String query,
    required String domainId,
    required String problemClass,
  }) {
    final slots = <String, dynamic>{};
    final city = problemFramer.extractCity(query);
    if (city.isNotEmpty) {
      slots[domainId == 'weather' ? 'city' : 'destination'] = city;
    }
    final budget = _extractBudget(query);
    if (budget.isNotEmpty) slots['budget'] = budget;
    final days = _extractDays(query);
    if (days.isNotEmpty) slots['days'] = days;
    final companion = _extractCompanionType(query);
    if (companion.isNotEmpty) slots['companionType'] = companion;
    if (problemClass == 'realtime_info' && city.isEmpty) {
      slots.remove('destination');
    }
    return slots;
  }

  String _extractBudget(String query) {
    final match = RegExp(
      r'预算\s*([0-9]+(?:\.[0-9]+)?\s*(?:元|块|w|万)?)',
    ).firstMatch(query);
    return (match?.group(1) ?? '').trim();
  }

  String _extractDays(String query) {
    final dayNight = RegExp(r'([0-9]+天[0-9]+晚)').firstMatch(query);
    if (dayNight != null) return (dayNight.group(1) ?? '').trim();
    final daysOnly = RegExp(r'([0-9]+天)').firstMatch(query);
    return (daysOnly?.group(1) ?? '').trim();
  }

  String _extractCompanionType(String query) {
    const labels = <String>['亲子', '情侣', '商务', '朋友', '家庭', '独自', '一个人'];
    for (final label in labels) {
      if (query.contains(label)) return label;
    }
    return '';
  }

  SlotValueSnapshot _normalizePayloadSlot(String slotId, Object? raw) {
    if (raw is Map) {
      final typed = raw.cast<String, dynamic>();
      if (typed['status'] != null || typed['value'] != null) {
        return SlotValueSnapshot.fromJson(slotId, typed).copyWith(
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
    final value = raw?.toString().trim() ?? '';
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
    final value = slot.value?.toString().trim() ?? '';
    if (value.isEmpty) return false;
    return slot.status != SlotValueStatus.missing &&
        slot.status != SlotValueStatus.conflicted;
  }

  String _defaultAskUserPrompt({
    required String slotId,
    required String domainId,
  }) {
    switch (slotId) {
      case 'city':
        return '告诉我要查的城市，比如“深圳”。';
      case 'destination':
        return '告诉我你准备去哪座城市或区域，我再继续帮你收敛。';
      case 'budget':
        return '再告诉我预算范围，我就能把建议压得更准。';
      case 'days':
        return '告诉我计划玩几天几晚，我可以直接按天数来排。';
      case 'companionType':
        return '再补一句同行类型，比如亲子、情侣或朋友出行。';
      default:
        return domainId == 'weather'
            ? '补一句你想查询的城市，我就继续。'
            : '再补一句最关键的条件，我就继续帮你收敛。';
    }
  }
}
