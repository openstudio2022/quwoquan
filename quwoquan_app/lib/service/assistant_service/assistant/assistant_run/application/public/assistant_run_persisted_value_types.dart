import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/aggregation_state.dart'
    as aggregation;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_journey.dart'
    as journey;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_display_state_projection.dart'
    as display;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_process_timeline.dart'
    as timeline;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/process_protocol.dart'
    as protocol;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/run_artifacts.dart'
    as artifacts;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/skill_run.dart'
    as skill_run;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/subagent_plan.dart'
    as subagent_plan;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/system_context_envelope.dart'
    as system_context;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/understanding_snapshot_codec.dart'
    as understanding_codec;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/understanding_result_contract.dart'
    as understanding;

typedef AssistantJourney = journey.AssistantJourney;
typedef AssistantJourneyStage = journey.AssistantJourneyStage;
typedef AggregationState = aggregation.AggregationState;
typedef RunArtifacts = artifacts.RunArtifacts;
typedef SkillRun = skill_run.SkillRun;
typedef SubagentPlan = subagent_plan.SubagentPlan;

extension AssistantJourneyPersistedSemantics on AssistantJourney {
  bool get isEmpty =>
      stages.isEmpty && entries.isEmpty && summary.trim().isEmpty;
}

typedef SlotStateSnapshot = artifacts.SlotStateSnapshot;
typedef RunArtifactsUnderstandingSnapshot =
    artifacts.RunArtifactsUnderstandingSnapshot;
typedef RunArtifactsAnswerProcessing = artifacts.RunArtifactsAnswerProcessing;
typedef RunArtifactsHistoricalThinkingSnapshot =
    artifacts.RunArtifactsHistoricalThinkingSnapshot;
typedef RetrievalProcessingSnapshot = artifacts.RetrievalProcessingSnapshot;
typedef ProcessTimelineFrame = artifacts.ProcessTimelineFrame;
typedef AssistantDisplayState = artifacts.AssistantDisplayState;
typedef AssistantAnswerDisplayBlock = artifacts.AssistantAnswerDisplayBlock;

RunArtifactsUnderstandingSnapshot parseRunArtifactsUnderstandingSnapshotFromMap(
  Map<String, dynamic> raw,
) {
  return understanding_codec.parseRunArtifactsUnderstandingSnapshotFromMap(raw);
}

typedef UnderstandingResult = understanding.UnderstandingResult;
typedef ProcessProtocolCode = protocol.ProcessProtocolCode;
typedef SystemContextEnvelope = system_context.SystemContextEnvelope;
const String assistantDisplayStateField = display.assistantDisplayStateField;

bool hasStructuredProcessTimeline(List<ProcessTimelineFrame> frames) {
  return timeline.hasStructuredProcessTimeline(frames);
}

List<ProcessTimelineFrame> normalizeProcessTimeline(
  List<ProcessTimelineFrame> frames,
) {
  return timeline.normalizeProcessTimeline(frames);
}

List<ProcessTimelineFrame> buildProcessTimelineFromSnapshots({
  List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
  RunArtifactsUnderstandingSnapshot understandingSnapshot =
      const RunArtifactsUnderstandingSnapshot(),
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
  RunArtifactsAnswerProcessing answerProcessing =
      const RunArtifactsAnswerProcessing(),
}) {
  return timeline.buildProcessTimelineFromSnapshots(
    processTimeline: processTimeline,
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    answerProcessing: answerProcessing,
  );
}

List<ProcessTimelineFrame> buildVisibleProcessTimeline(
  List<ProcessTimelineFrame> frames,
) {
  return timeline.buildVisibleProcessTimeline(frames);
}

AssistantDisplayState parseAssistantDisplayStateFromMap(
  Map<String, dynamic>? raw,
) {
  return display.parseAssistantDisplayStateFromMap(raw);
}

bool hasAssistantDisplayState(AssistantDisplayState state) {
  return display.hasAssistantDisplayState(state);
}

String renderAnswerBlocksToMarkdown(List<AssistantAnswerDisplayBlock> blocks) {
  return display.renderAnswerBlocksToMarkdown(blocks);
}

String renderAnswerBlocksToPlainText(List<AssistantAnswerDisplayBlock> blocks) {
  return display.renderAnswerBlocksToPlainText(blocks);
}
