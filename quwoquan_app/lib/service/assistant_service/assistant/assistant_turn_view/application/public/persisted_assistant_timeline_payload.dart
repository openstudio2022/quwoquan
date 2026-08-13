import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_persisted_value_types.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/orchestrator_state_contract.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/public/task_graph_view.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/turn_synthesis_state_contract.dart';

/// C4 持久化键名（时间轴 assistant_turn 子图的唯一键空间声明处）。
const String assistantJourneyField = 'journey';
const String assistantProcessTimelineField = 'processTimeline';
const String assistantDisplayMarkdownField = 'displayMarkdown';
const String assistantDisplayPlainTextField = 'displayPlainText';
const String assistantFollowupPromptField = 'followupPrompt';
const String assistantActionHintsField = 'actionHints';
const String assistantUnderstandingSnapshotField = 'understandingSnapshot';
const String assistantAnswerProcessingField = 'answerProcessing';
const String assistantHistoricalThinkingSnapshotField =
    'historicalThinkingSnapshot';
const String assistantRetrievalProcessingField = 'retrievalProcessing';
const String assistantProviderReasoningContinuationField =
    'providerReasoningContinuation';
const String assistantSystemContextEnvelopeField = 'systemContextEnvelope';
const String assistantUnderstandingResultField = 'understandingResult';
const String assistantTaskGraphField = 'taskGraph';
const String assistantOrchestratorStateField = 'orchestratorState';
const String assistantTurnSynthesisStateField = 'turnSynthesisState';
const String assistantElapsedMsField = 'assistantElapsedMs';

/// C4 持久化块允许的顶层键（与 [PersistedAssistantTimelinePayload.toMap] 及
/// controller spread 对齐）。
const Set<String> kPersistedAssistantTimelinePayloadKeys = {
  assistantJourneyField,
  assistantProcessTimelineField,
  assistantUnderstandingSnapshotField,
  assistantAnswerProcessingField,
  assistantHistoricalThinkingSnapshotField,
  assistantRetrievalProcessingField,
  assistantProviderReasoningContinuationField,
  assistantSystemContextEnvelopeField,
  assistantUnderstandingResultField,
  assistantTaskGraphField,
  assistantOrchestratorStateField,
  assistantTurnSynthesisStateField,
  assistantDisplayStateField,
  assistantDisplayMarkdownField,
  assistantDisplayPlainTextField,
  assistantFollowupPromptField,
  assistantActionHintsField,
  assistantElapsedMsField,
};

String _sanitizeUserFacingTimelineText(String raw) {
  final normalized =
      AssistantDisplayTextResolver.normalizeUserFacingProcessNarration(raw);
  if (normalized.isEmpty) {
    return '';
  }
  if (AssistantDisplayTextResolver.containsInternalProcessFragment(
    normalized,
  )) {
    return '';
  }
  return normalized;
}

Map<String, dynamic>? _structuredMap(Object? raw) {
  if (raw is! Map) {
    return null;
  }
  final map = raw.cast<String, dynamic>();
  for (final item in map.values) {
    if (item is String && item.trim().isNotEmpty) return map;
    if (item is num && item != 0) return map;
    if (item is bool && item) return map;
    if (item is List && item.isNotEmpty) return map;
    if (item is Map && item.isNotEmpty) return map;
  }
  return null;
}

List<ProcessTimelineFrame> _parseProcessTimelineList(Object? raw) {
  if (raw is! List) {
    return const <ProcessTimelineFrame>[];
  }
  final frames = raw
      .whereType<Map>()
      .map(
        (item) => ProcessTimelineFrame.fromJson(item.cast<String, dynamic>()),
      )
      .toList(growable: false);
  return normalizeProcessTimeline(frames);
}

/// C4：时间轴上的 assistant_turn 持久化子图（不含 sender / runId 等信封键）。
///
/// 曾是 `_entries: Map<String, dynamic>` 稀疏袋 + 一组
/// `resolvePersisted*(Map message)` 惰性解析函数；解码现在在磁盘边界
/// （[fromMap]，由 Codec 调用）一次完成，之后全程 typed，UI 不再经
/// encode -> Map -> resolve 的往返桥取值。
class PersistedAssistantTimelinePayload {
  const PersistedAssistantTimelinePayload({
    this.journey,
    this.processTimeline = const <ProcessTimelineFrame>[],
    this.understandingSnapshot,
    this.answerProcessing,
    this.historicalThinkingSnapshot,
    this.retrievalProcessing,
    this.providerReasoningContinuation = '',
    this.systemContextEnvelope,
    this.understandingResult,
    this.taskGraph,
    this.orchestratorState,
    this.turnSynthesisState,
    this.displayState,
    this.displayMarkdown = '',
    this.displayPlainText = '',
    this.followupPrompt = '',
    this.actionHints = const <String>[],
    this.assistantElapsedMs = 0,
  });

  final AssistantJourney? journey;
  final List<ProcessTimelineFrame> processTimeline;
  final RunArtifactsUnderstandingSnapshot? understandingSnapshot;
  final RunArtifactsAnswerProcessing? answerProcessing;
  final RunArtifactsHistoricalThinkingSnapshot? historicalThinkingSnapshot;
  final RetrievalProcessingSnapshot? retrievalProcessing;
  final String providerReasoningContinuation;
  final SystemContextEnvelope? systemContextEnvelope;
  final UnderstandingResult? understandingResult;
  final TaskGraph? taskGraph;
  final SessionOrchestratorState? orchestratorState;
  final TurnSynthesisState? turnSynthesisState;
  final AssistantDisplayState? displayState;
  final String displayMarkdown;
  final String displayPlainText;
  final String followupPrompt;
  final List<String> actionHints;
  final int assistantElapsedMs;

  /// 空持久化块（流式占位等）。
  factory PersistedAssistantTimelinePayload.empty() {
    return const PersistedAssistantTimelinePayload();
  }

  /// 磁盘/协议 Map 边界的唯一解码入口（Codec 与测试 fixture 使用）。
  ///
  /// 宽容度与既往惰性 resolve 完全一致：缺键、非 Map、以及全空值的结构体
  /// 均视为「未设置」；结构化内容交给各 typed `fromJson` fail-closed 解析。
  factory PersistedAssistantTimelinePayload.fromMap(Map<String, dynamic> m) {
    AssistantJourney? journey;
    final journeyRaw = (m[assistantJourneyField] as Map?)
        ?.cast<String, dynamic>();
    if (journeyRaw != null && journeyRaw.isNotEmpty) {
      final parsed = AssistantJourney.fromJson(journeyRaw);
      journey = parsed.isEmpty ? null : parsed;
    }

    final understandingSnapshotRaw = _structuredMap(
      m[assistantUnderstandingSnapshotField],
    );
    final answerProcessingRaw = _structuredMap(m[assistantAnswerProcessingField]);
    final historicalRaw = _structuredMap(
      m[assistantHistoricalThinkingSnapshotField],
    );
    final retrievalRaw = _structuredMap(m[assistantRetrievalProcessingField]);
    final envelopeRaw = _structuredMap(m[assistantSystemContextEnvelopeField]);
    final understandingResultRaw = _structuredMap(
      m[assistantUnderstandingResultField],
    );
    final taskGraphRaw = _structuredMap(m[assistantTaskGraphField]);
    final orchestratorRaw = _structuredMap(m[assistantOrchestratorStateField]);
    final synthesisRaw = _structuredMap(m[assistantTurnSynthesisStateField]);

    final displayState = parseAssistantDisplayStateFromMap(
      (m[assistantDisplayStateField] as Map?)?.cast<String, dynamic>(),
    );

    return PersistedAssistantTimelinePayload(
      journey: journey,
      processTimeline: _parseProcessTimelineList(
        m[assistantProcessTimelineField],
      ),
      understandingSnapshot: understandingSnapshotRaw == null
          ? null
          : parseRunArtifactsUnderstandingSnapshotFromMap(
              understandingSnapshotRaw,
            ),
      answerProcessing: answerProcessingRaw == null
          ? null
          : RunArtifactsAnswerProcessing.fromJson(answerProcessingRaw),
      historicalThinkingSnapshot: historicalRaw == null
          ? null
          : RunArtifactsHistoricalThinkingSnapshot.fromJson(historicalRaw),
      retrievalProcessing: retrievalRaw == null
          ? null
          : RetrievalProcessingSnapshot.fromJson(retrievalRaw),
      providerReasoningContinuation:
          (m[assistantProviderReasoningContinuationField] as String?)?.trim() ??
          '',
      systemContextEnvelope: envelopeRaw == null
          ? null
          : SystemContextEnvelope.fromJson(envelopeRaw),
      understandingResult: understandingResultRaw == null
          ? null
          : UnderstandingResult.fromJson(understandingResultRaw),
      taskGraph: taskGraphRaw == null ? null : TaskGraph.fromJson(taskGraphRaw),
      orchestratorState: orchestratorRaw == null
          ? null
          : SessionOrchestratorState.fromJson(orchestratorRaw),
      turnSynthesisState: synthesisRaw == null
          ? null
          : TurnSynthesisState.fromJson(synthesisRaw),
      displayState: hasAssistantDisplayState(displayState)
          ? displayState
          : null,
      displayMarkdown:
          (m[assistantDisplayMarkdownField] as String?)?.trim() ?? '',
      displayPlainText:
          (m[assistantDisplayPlainTextField] as String?)?.trim() ?? '',
      followupPrompt: (m[assistantFollowupPromptField] as String?) ?? '',
      actionHints:
          ((m[assistantActionHintsField] as List?) ?? const <Object?>[])
              .whereType<String>()
              .toList(growable: false),
      assistantElapsedMs: (m[assistantElapsedMsField] as num?)?.toInt() ?? 0,
    );
  }

  /// 完整轮次的 typed 构造（原 `buildPersistedAssistantTurnFields` 的替代）：
  /// 补全 process timeline、规范化展示文案、清洗用户可见文本。
  factory PersistedAssistantTimelinePayload.build({
    required AssistantJourney journey,
    required String displayMarkdown,
    required String displayPlainText,
    required String followupPrompt,
    required List<String> actionHints,
    required int elapsedMs,
    AssistantDisplayState? displayState,
    List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
    RunArtifactsUnderstandingSnapshot? understandingSnapshot,
    RunArtifactsAnswerProcessing? answerProcessing,
    RunArtifactsHistoricalThinkingSnapshot? historicalThinkingSnapshot,
    RetrievalProcessingSnapshot? retrievalProcessing,
    SystemContextEnvelope? systemContextEnvelope,
    UnderstandingResult? understandingResult,
    TaskGraph? taskGraph,
    SessionOrchestratorState? orchestratorState,
    TurnSynthesisState? turnSynthesisState,
    String providerReasoningContinuation = '',
  }) {
    final persistedProcessTimeline =
        hasStructuredProcessTimeline(processTimeline)
        ? normalizeProcessTimeline(processTimeline)
        : buildProcessTimelineFromSnapshots(
            understandingSnapshot:
                understandingSnapshot ??
                const RunArtifactsUnderstandingSnapshot(),
            retrievalProcessing:
                retrievalProcessing ?? const RetrievalProcessingSnapshot(),
            answerProcessing:
                answerProcessing ?? const RunArtifactsAnswerProcessing(),
          );
    return PersistedAssistantTimelinePayload(
      journey: journey,
      processTimeline: hasStructuredProcessTimeline(persistedProcessTimeline)
          ? persistedProcessTimeline
          : const <ProcessTimelineFrame>[],
      understandingSnapshot: understandingSnapshot,
      answerProcessing: answerProcessing,
      historicalThinkingSnapshot: historicalThinkingSnapshot,
      retrievalProcessing: retrievalProcessing,
      providerReasoningContinuation: providerReasoningContinuation.trim(),
      systemContextEnvelope: systemContextEnvelope,
      understandingResult: understandingResult,
      taskGraph: taskGraph,
      orchestratorState: orchestratorState,
      turnSynthesisState: turnSynthesisState,
      displayState: displayState != null &&
              hasAssistantDisplayState(displayState)
          ? displayState
          : null,
      displayMarkdown:
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
        displayMarkdown,
        allowJsonExtraction: false,
      ),
      displayPlainText:
          AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
        displayPlainText,
        allowJsonExtraction: false,
      ),
      followupPrompt: _sanitizeUserFacingTimelineText(followupPrompt),
      actionHints: actionHints
          .map(_sanitizeUserFacingTimelineText)
          .where((item) => item.isNotEmpty)
          .toList(growable: false),
      assistantElapsedMs: elapsedMs,
    );
  }

  /// 磁盘/协议 Map 边界的唯一编码出口：只写有内容的键（稀疏语义）。
  Map<String, dynamic> toMap() => <String, dynamic>{
        if (journey != null) assistantJourneyField: journey!.toJson(),
        if (processTimeline.isNotEmpty)
          assistantProcessTimelineField: processTimeline
              .map((item) => item.toJson())
              .toList(growable: false),
        if (understandingSnapshot != null)
          assistantUnderstandingSnapshotField: understandingSnapshot!.toJson(),
        if (answerProcessing != null)
          assistantAnswerProcessingField: answerProcessing!.toJson(),
        if (historicalThinkingSnapshot != null)
          assistantHistoricalThinkingSnapshotField:
              historicalThinkingSnapshot!.toJson(),
        if (retrievalProcessing != null)
          assistantRetrievalProcessingField: retrievalProcessing!.toJson(),
        if (providerReasoningContinuation.isNotEmpty)
          assistantProviderReasoningContinuationField:
              providerReasoningContinuation,
        if (systemContextEnvelope != null)
          assistantSystemContextEnvelopeField:
              systemContextEnvelope!.toJson(),
        if (understandingResult != null)
          assistantUnderstandingResultField: understandingResult!.toJson(),
        if (taskGraph != null) assistantTaskGraphField: taskGraph!.toJson(),
        if (orchestratorState != null)
          assistantOrchestratorStateField: orchestratorState!.toJson(),
        if (turnSynthesisState != null)
          assistantTurnSynthesisStateField: turnSynthesisState!.toJson(),
        if (displayState != null)
          assistantDisplayStateField: displayState!.toJson(),
        if (displayMarkdown.isNotEmpty)
          assistantDisplayMarkdownField: displayMarkdown,
        if (displayPlainText.isNotEmpty)
          assistantDisplayPlainTextField: displayPlainText,
        if (followupPrompt.isNotEmpty)
          assistantFollowupPromptField: followupPrompt,
        if (actionHints.isNotEmpty) assistantActionHintsField: actionHints,
        if (assistantElapsedMs != 0)
          assistantElapsedMsField: assistantElapsedMs,
      };

  /// 流式增量合并：patch 中出现的键整键覆盖，`null` 删除，未出现保留。
  /// 键空间外的 patch 项被忽略（与 [fromMap] 的过滤一致）。
  PersistedAssistantTimelinePayload copyWithMerged(
    Map<String, dynamic> patch,
  ) {
    final merged = toMap();
    for (final entry in patch.entries) {
      if (!kPersistedAssistantTimelinePayloadKeys.contains(entry.key)) {
        continue;
      }
      if (entry.value == null) {
        merged.remove(entry.key);
      } else {
        merged[entry.key] = entry.value;
      }
    }
    return PersistedAssistantTimelinePayload.fromMap(merged);
  }

  /// 可见 process timeline：直接帧优先，缺结构化帧时由各 snapshot 合成。
  List<ProcessTimelineFrame> get visibleProcessTimeline {
    final supplemented = buildProcessTimelineFromSnapshots(
      processTimeline: hasStructuredProcessTimeline(processTimeline)
          ? processTimeline
          : const <ProcessTimelineFrame>[],
      understandingSnapshot:
          understandingSnapshot ?? const RunArtifactsUnderstandingSnapshot(),
      retrievalProcessing:
          retrievalProcessing ?? const RetrievalProcessingSnapshot(),
      answerProcessing:
          answerProcessing ?? const RunArtifactsAnswerProcessing(),
    );
    if (!hasStructuredProcessTimeline(supplemented)) {
      return const <ProcessTimelineFrame>[];
    }
    return buildVisibleProcessTimeline(supplemented);
  }

  /// 展示 Markdown：displayState 的 answer blocks 优先，否则规范化字符串字段。
  String get resolvedDisplayMarkdown {
    final state = displayState;
    if (state != null && state.answer.blocks.isNotEmpty) {
      return renderAnswerBlocksToMarkdown(state.answer.blocks);
    }
    return AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
      displayMarkdown,
      allowJsonExtraction: false,
    );
  }

  String get resolvedDisplayPlainText {
    final state = displayState;
    if (state != null && state.answer.blocks.isNotEmpty) {
      return renderAnswerBlocksToPlainText(state.answer.blocks);
    }
    return AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
      displayPlainText,
      allowJsonExtraction: false,
    );
  }

  /// 历史数据双保险：读取侧再次清洗用户可见文本（写入侧 build 已清洗一遍）。
  String get sanitizedFollowupPrompt =>
      _sanitizeUserFacingTimelineText(followupPrompt);

  List<String> get sanitizedActionHints => actionHints
      .map(_sanitizeUserFacingTimelineText)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}
