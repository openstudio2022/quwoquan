import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

Map<String, dynamic> buildConversationSpine({
  required String stageId,
  required String userQuery,
  String userGoal = '',
  String primarySkill = '',
  String problemClass = '',
  String answerShape = '',
  Map<String, dynamic> historyAssessment = const <String, dynamic>{},
  Map<String, dynamic> stageState = const <String, dynamic>{},
}) {
  return _compactMap(<String, dynamic>{
    'stageId': stageId.trim(),
    'currentTurn': _compactMap(<String, dynamic>{
      'userQuery': userQuery.trim(),
      'userGoal': userGoal.trim(),
      'primarySkill': primarySkill.trim(),
      'problemClass': problemClass.trim(),
      'answerShape': answerShape.trim(),
    }),
    'historyAssessment': mergeHistoryAssessments(
      <Map<String, dynamic>>[historyAssessment],
    ),
    'stageState': _compactMap(stageState),
  });
}

Map<String, dynamic> buildHistoryAssessmentFromPolicy({
  required ContextContinuityPolicy policy,
  Map<String, dynamic> overrideSlots = const <String, dynamic>{},
}) {
  return buildHistoryAssessment(
    continuityMode: policy.continuityMode.wireName,
    mismatchSignal: policy.mismatchSignal,
    carryForwardFacts: policy.carryForwardFacts,
    needsRecheckFacts: policy.needsRecheckFacts,
    discardedAssumptions: policy.discardedAssumptions,
    overrideSlots: overrideSlots,
  );
}

Map<String, dynamic> buildHistoryAssessmentFromSnapshot({
  required RunArtifactsHistoricalThinkingSnapshot snapshot,
  Map<String, dynamic> overrideSlots = const <String, dynamic>{},
}) {
  return buildHistoryAssessment(
    continuityMode: snapshot.continuityMode,
    mismatchSignal: snapshot.mismatchSignal,
    carryForwardFacts: snapshot.carryForwardFacts,
    needsRecheckFacts: snapshot.needsRecheckFacts,
    discardedAssumptions: snapshot.discardedAssumptions,
    overrideSlots: overrideSlots,
  );
}

Map<String, dynamic> buildHistoryAssessment({
  String continuityMode = '',
  String mismatchSignal = '',
  Iterable<String> carryForwardFacts = const <String>[],
  Iterable<String> needsRecheckFacts = const <String>[],
  Iterable<String> discardedAssumptions = const <String>[],
  Map<String, dynamic> overrideSlots = const <String, dynamic>{},
}) {
  return _compactMap(<String, dynamic>{
    'continuityMode': continuityMode.trim(),
    'mismatchSignal': mismatchSignal.trim(),
    'carryForwardFacts': _normalizeStrings(carryForwardFacts),
    'needsRecheckFacts': _normalizeStrings(needsRecheckFacts),
    'discardedAssumptions': _normalizeStrings(discardedAssumptions),
    'overrideSlots': _compactMap(overrideSlots),
  });
}

Map<String, dynamic> mergeHistoryAssessments(
  Iterable<Map<String, dynamic>> assessments,
) {
  var continuityMode = '';
  var mismatchSignal = '';
  final carryForwardFacts = <String>[];
  final needsRecheckFacts = <String>[];
  final discardedAssumptions = <String>[];
  var overrideSlots = const <String, dynamic>{};
  for (final assessment in assessments) {
    if (assessment.isEmpty) continue;
    final candidateContinuityMode =
        (assessment['continuityMode'] as String?)?.trim() ?? '';
    if (continuityMode.isEmpty && candidateContinuityMode.isNotEmpty) {
      continuityMode = candidateContinuityMode;
    }
    final candidateMismatchSignal =
        (assessment['mismatchSignal'] as String?)?.trim() ?? '';
    if (mismatchSignal.isEmpty && candidateMismatchSignal.isNotEmpty) {
      mismatchSignal = candidateMismatchSignal;
    }
    _appendUniqueStrings(carryForwardFacts, assessment['carryForwardFacts']);
    _appendUniqueStrings(needsRecheckFacts, assessment['needsRecheckFacts']);
    _appendUniqueStrings(
      discardedAssumptions,
      assessment['discardedAssumptions'],
    );
    if (overrideSlots.isEmpty && assessment['overrideSlots'] is Map) {
      overrideSlots =
          (assessment['overrideSlots'] as Map).cast<String, dynamic>();
    }
  }
  return buildHistoryAssessment(
    continuityMode: continuityMode,
    mismatchSignal: mismatchSignal,
    carryForwardFacts: carryForwardFacts,
    needsRecheckFacts: needsRecheckFacts,
    discardedAssumptions: discardedAssumptions,
    overrideSlots: overrideSlots,
  );
}

List<String> _normalizeStrings(Iterable<String> values) {
  final out = <String>[];
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty || out.contains(normalized)) {
      continue;
    }
    out.add(normalized);
  }
  return out;
}

void _appendUniqueStrings(List<String> out, Object? raw) {
  if (raw is! List) return;
  for (final item in raw) {
    final normalized = item.toString().trim();
    if (normalized.isEmpty || out.contains(normalized)) {
      continue;
    }
    out.add(normalized);
  }
}

Map<String, dynamic> _compactMap(Map<String, dynamic> raw) {
  final out = <String, dynamic>{};
  for (final entry in raw.entries) {
    final value = entry.value;
    if (value == null) continue;
    if (value is String && value.trim().isEmpty) continue;
    if (value is List && value.isEmpty) continue;
    if (value is Map && value.isEmpty) continue;
    out[entry.key] = value;
  }
  return out;
}
