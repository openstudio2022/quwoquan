import 'package:quwoquan_app/assistant/contracts/context_fill_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/context/assembly/continuity_resolver.dart';

/// Plans context gaps: slots, evidence, long-term memory, preferences, location,
/// or ask_user. Uses [ResolvedContinuity] and optionally [RunArtifacts].
class ContextGapPlanner {
  const ContextGapPlanner();

  /// Plans fill tasks for missing context. When [runArtifacts] is provided,
  /// can restore and carry over slots from the previous run.
  List<ContextFillTask> planGaps({
    required ResolvedContinuity resolvedContinuity,
    required ContextAssemblyResult contextAssembly,
    required String query,
    RunArtifacts? runArtifacts,
    List<String> recalledTexts = const [],
  }) {
    final fillTasks = <ContextFillTask>[];
    final missingSlots =
        (contextAssembly.contextEnvelope['missingSlots'] as List?)
            ?.whereType<String>()
            .toList(growable: false) ??
        <String>[];

    if (contextAssembly.hasLongtermNeed && recalledTexts.isEmpty) {
      if (!missingSlots.contains('longterm_memory')) {
        fillTasks.add(
          const ContextFillTask(
            fillType: ContextFillType.contextFill,
            targetSlot: ContextTargetSlot.longtermMemory,
            reason: '',
            generatedQueryConditions: [],
            scopeExpansionPolicy: ContextScopeExpansionPolicy.expandTimeWindow,
          ),
        );
      }
    }

    final typedProblemClass =
        (contextAssembly.contextEnvelope['typedSignals'] as Map?)
            ?.cast<String, dynamic>()['problemClass']
            ?.toString()
            .trim() ??
        '';
    if (parseProblemClass(typedProblemClass) == ProblemClass.realtimeInfo) {
      final sourceStatus =
          (contextAssembly.contextEnvelope['sourceStatus'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final realtimeEvidence = sourceStatus['realtimeEvidence'];
      if (realtimeEvidence != 'ready') {
        fillTasks.add(
          ContextFillTask(
            fillType: ContextFillType.replan,
            targetSlot: ContextTargetSlot.realtimeEvidence,
            reason: '',
            generatedQueryConditions: [query],
            scopeExpansionPolicy:
                ContextScopeExpansionPolicy.expandScopeAndRequery,
          ),
        );
      }
    }

    if (runArtifacts != null && resolvedContinuity.slotsToCarry.isNotEmpty) {
      final slotState = runArtifacts.slotState;
      for (final slotId in slotState.missingSlots) {
        if (!fillTasks.any((t) => t.targetSlot.wireName == slotId)) {
          fillTasks.add(
            ContextFillTask(
              fillType: ContextFillType.contextFill,
              targetSlot: parseContextTargetSlot(slotId),
              reason: '',
              generatedQueryConditions: [query],
              scopeExpansionPolicy: ContextScopeExpansionPolicy.none,
            ),
          );
        }
      }
    }

    return fillTasks;
  }
}
