import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

/// Result of resolving continuity: fresh topic, same topic, active task
/// continuation, or override follow-up. Used by [ContextGapPlanner].
class ResolvedContinuity {
  const ResolvedContinuity({
    required this.mode,
    required this.policy,
    this.activeTaskId,
    this.slotsToCarry = const <String, SlotValueSnapshot>{},
    this.overrideSlots = const <String, dynamic>{},
  });

  final ContextContinuityMode mode;
  final ContextContinuityPolicy policy;

  /// Non-null when this is a follow-up to an unfinished task from a prior run.
  final String? activeTaskId;

  /// Slots to carry from previous run (e.g. location, time).
  final Map<String, SlotValueSnapshot> slotsToCarry;

  /// User override values (e.g. "改成上海" overrides location).
  final Map<String, dynamic> overrideSlots;

  bool get isFollowUp =>
      mode == ContextContinuityMode.sameTopic ||
      mode == ContextContinuityMode.explicitFollowUp;

  bool get isActiveTaskContinuation => activeTaskId != null;
}

/// Resolves continuity: fresh topic / same topic / active task continuation /
/// override follow-up. Uses session history and optional [RunArtifacts] to
/// restore follow-up state.
class ContinuityResolver {
  const ContinuityResolver();

  ResolvedContinuity resolve({
    required String query,
    required List<Map<String, dynamic>> sessionHistory,
    required ContextContinuityPolicy basePolicy,
    RunArtifacts? previousRunArtifacts,
  }) {
    final policy = basePolicy;
    String? activeTaskId;
    final slotsToCarry = <String, SlotValueSnapshot>{};
    final overrideSlots = <String, dynamic>{};

    if (previousRunArtifacts != null && policy.continuityMode != ContextContinuityMode.freshTopic) {
      final slotState = previousRunArtifacts.slotState;
      if (slotState.slotValues.isNotEmpty) {
        for (final entry in slotState.slotValues.entries) {
          final v = entry.value;
          if (v.slotId.trim().isNotEmpty) {
            slotsToCarry[v.slotId] = v;
          }
        }
      }
    }

    return ResolvedContinuity(
      mode: policy.continuityMode,
      policy: policy,
      activeTaskId: activeTaskId,
      slotsToCarry: slotsToCarry,
      overrideSlots: overrideSlots,
    );
  }
}
