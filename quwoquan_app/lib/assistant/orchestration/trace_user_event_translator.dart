import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/tool_assessment.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class TraceUserEventTranslator {
  static UserEvent? translate(AssistantTraceEvent event) {
    if (!event.visibility.isUserVisible) return null;
    final data = event.data ?? const <String, dynamic>{};
    switch (event.type) {
      case AssistantTraceEventType.planStarted:
        const phaseId = PlannerPhaseId.understanding;
        final isRealtime = _isRealtimeProblemClass(data);
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.root,
          nodeId: 'root.intent.plan',
          runId: event.runId ?? '',
          phaseId: phaseId,
          actionCode: PlannerActionCode.frameProblem,
          reasonCode: isRealtime
              ? PlannerReasonCode.confirmRealtimeScope
              : PlannerReasonCode.alignGoal,
          reasonShort: _buildPlanStartedMessage(data),
        );
      case AssistantTraceEventType.thinkingStarted:
        final stage = _resolveThinkingStage(data);
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: _scopeForStage(stage),
          nodeId: _thinkingIntroNodeId(stage),
          runId: event.runId ?? '',
          phaseId: stage,
          actionCode: stage == PlannerPhaseId.answering
              ? PlannerActionCode.composeAnswer
              : PlannerActionCode.assessEvidence,
          reasonCode: stage == PlannerPhaseId.analyzing
              ? PlannerReasonCode.checkConsistency
              : stage == PlannerPhaseId.answering
              ? PlannerReasonCode.prepareDelivery
              : PlannerReasonCode.confirmFocus,
          reasonShort: _buildThinkingStartedMessage(stage, data),
        );
      case AssistantTraceEventType.thinkingProgress:
        final stage = _resolveThinkingStage(data);
        final message = _buildThinkingProgressMessage(stage, data);
        final isStreaming = data['streaming'] == true;
        return _buildEvent(
          type: isStreaming
              ? UserEventType.processReplace
              : UserEventType.processAppend,
          scope: _scopeForStage(stage),
          nodeId: _thinkingStreamNodeId(stage),
          runId: event.runId ?? '',
          phaseId: stage,
          actionCode: stage == PlannerPhaseId.answering
              ? PlannerActionCode.composeAnswer
              : PlannerActionCode.assessEvidence,
          reasonCode: stage == PlannerPhaseId.analyzing
              ? PlannerReasonCode.checkConsistency
              : stage == PlannerPhaseId.answering
              ? PlannerReasonCode.prepareDelivery
              : PlannerReasonCode.confirmFocus,
          reasonShort: message,
          extraPayload: <String, dynamic>{if (isStreaming) 'streaming': true},
        );
      case AssistantTraceEventType.searchQueryGenerated:
        final toolName = _toolName(data);
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: _searchPlanNodeId(toolName),
          runId: event.runId ?? '',
          phaseId: PlannerPhaseId.searching,
          actionCode: PlannerActionCode.startRetrieval,
          reasonCode: _searchTaskCount(data) > 1
              ? PlannerReasonCode.reduceWaitTime
              : PlannerReasonCode.targetedProbe,
          reasonShort: _buildToolStartMessage(data),
          extraPayload: <String, dynamic>{
            'toolName': toolName,
            if (data['queryTasks'] is List)
              'queryTaskCount': _searchTaskCount(data),
          },
        );
      case AssistantTraceEventType.searchStarted:
        final toolName = _toolName(data);
        return _buildEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: _searchPlanNodeId(toolName),
          runId: event.runId ?? '',
          phaseId: PlannerPhaseId.searching,
          actionCode: PlannerActionCode.startRetrieval,
          reasonCode: PlannerReasonCode.targetedProbe,
          reasonShort: _buildToolStartMessage(data),
          extraPayload: <String, dynamic>{'toolName': toolName},
        );
      case AssistantTraceEventType.toolResult:
        if (data['isAssessment'] == true) {
          final assessment = _toolAssessmentFromData(data);
          final userMessage = _buildAssessmentMessage(data);
          if (userMessage.isEmpty) return null;
          final phaseId =
              assessment.assessmentType == AssessmentType.needMoreSearch &&
                  assessment.shouldContinueLoop
              ? PlannerPhaseId.expanding
              : PlannerPhaseId.analyzing;
          return _buildEvent(
            type: UserEventType.processAppend,
            scope: UserEventScope.aggregation,
            nodeId: 'aggregation.assessment',
            runId: event.runId ?? '',
            phaseId: phaseId,
            actionCode: PlannerActionCode.assessEvidence,
            reasonCode: _assessmentReasonCode(data),
            reasonShort: userMessage,
          );
        }
        return null;
      case AssistantTraceEventType.searchCompleted:
        final refs = (data['references'] as List?)?.length ?? 0;
        final references =
            (data['references'] as List?)
                ?.whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .map(
                  (item) => <String, dynamic>{
                    'title': (item['title'] as String?)?.trim() ?? '',
                    'url': (item['url'] as String?)?.trim() ?? '',
                    'source': (item['source'] as String?)?.trim() ?? '',
                  },
                )
                .where(
                  (item) =>
                      (item['title'] as String).isNotEmpty &&
                      (item['url'] as String).isNotEmpty,
                )
                .take(6)
                .toList(growable: false) ??
            const <Map<String, dynamic>>[];
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: _searchResultNodeId(_toolName(data)),
          runId: event.runId ?? '',
          phaseId: PlannerPhaseId.searching,
          actionCode: PlannerActionCode.reviewSources,
          reasonCode: refs >= 3
              ? PlannerReasonCode.crossCheckSources
              : PlannerReasonCode.validateSource,
          reasonShort: _buildToolResultMessage(data, refs),
          extraPayload: <String, dynamic>{
            'referenceCount': refs,
            'references': references,
          },
        );
      case AssistantTraceEventType.toolError:
        if (data['retrievalLike'] != true) return null;
        return _buildEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: _searchResultNodeId(_toolName(data)),
          runId: event.runId ?? '',
          phaseId: PlannerPhaseId.searching,
          actionCode: PlannerActionCode.recoverRetrieval,
          reasonCode: PlannerReasonCode.sourceUnstable,
          reasonShort: _buildToolErrorMessage(data, event.message),
        );
      case AssistantTraceEventType.subagentStart:
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: _subagentPlanNodeId(data),
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          phaseId: PlannerPhaseId.searching,
          actionCode: PlannerActionCode.parallelProbe,
          reasonCode: PlannerReasonCode.reduceWaitTime,
          reasonShort: _buildSubagentStartMessage(),
        );
      case AssistantTraceEventType.subagentResult:
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: _subagentResultNodeId(data),
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          phaseId: PlannerPhaseId.analyzing,
          actionCode: PlannerActionCode.mergeParallelResult,
          reasonCode: PlannerReasonCode.evidenceBack,
          reasonShort: _summarizeSubtask(data),
        );
      case AssistantTraceEventType.subagentError:
        return _buildEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: _subagentResultNodeId(data),
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          phaseId: PlannerPhaseId.analyzing,
          actionCode: PlannerActionCode.fallbackWithExistingEvidence,
          reasonCode: PlannerReasonCode.parallelBranchFailed,
          reasonShort: '并行补充的这一支还不够稳，我继续用已经确认的部分往下收敛。',
        );
      case AssistantTraceEventType.lifecycleStart:
        if (data['phaseNarrative'] == true) {
          final narrative = (data['narrative'] as String?)?.trim() ??
              event.message.trim();
          if (narrative.isEmpty) return null;
          final phase = _plannerPhaseForNarrative(
            (data['phaseId'] as String?)?.trim() ?? '',
          );
          return _buildEvent(
            type: UserEventType.processCommit,
            scope: UserEventScope.root,
            nodeId: 'root.phase.${data['phaseId'] ?? 'bootstrap'}',
            runId: event.runId ?? '',
            phaseId: phase,
            actionCode: _plannerActionForNarrativePhase(phase),
            reasonCode: _plannerReasonForNarrativePhase(phase),
            reasonShort: narrative,
          );
        }
        return null;
      case AssistantTraceEventType.lifecycleEnd:
        final userMessage = _buildLifecycleEndMessage(data);
        if (userMessage.isEmpty) return null;
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.aggregation,
          nodeId: 'aggregation.final',
          runId: event.runId ?? '',
          phaseId: PlannerPhaseId.completed,
          actionCode: PlannerActionCode.completeTurn,
          reasonCode: PlannerReasonCode.readyToAnswer,
          reasonShort: userMessage,
        );
      default:
        return null;
    }
  }

  static UserEvent _buildEvent({
    required UserEventType type,
    required UserEventScope scope,
    required String nodeId,
    required PlannerPhaseId phaseId,
    required PlannerActionCode actionCode,
    required PlannerReasonCode reasonCode,
    required String reasonShort,
    String runId = '',
    Map<String, dynamic> extraPayload = const <String, dynamic>{},
  }) {
    return UserEvent(
      type: type,
      scope: scope,
      nodeId: nodeId,
      runId: runId,
      message: reasonShort,
      payload: <String, dynamic>{
        'stage': phaseId.wireName,
        'phaseId': phaseId.wireName,
        'actionCode': actionCode.wireName,
        'reasonCode': reasonCode.wireName,
        'reasonShort': reasonShort,
        'source': 'trace_translator',
        ...extraPayload,
      },
    );
  }

  static String _toolName(Map<String, dynamic> data) {
    return (data['toolName'] ?? data['tool'] ?? '').toString().trim();
  }

  static PlannerPhaseId _plannerPhaseForNarrative(String phaseId) {
    switch (phaseId) {
      case 'bootstrap':
      case 'understand':
        return PlannerPhaseId.understanding;
      case 'retrieval_design':
        return PlannerPhaseId.planning;
      case 'execution':
        return PlannerPhaseId.executing;
      case 'synthesis':
        return PlannerPhaseId.answering;
      case 'finalize':
        return PlannerPhaseId.completed;
      default:
        return PlannerPhaseId.understanding;
    }
  }

  static PlannerActionCode _plannerActionForNarrativePhase(
    PlannerPhaseId phase,
  ) {
    switch (phase) {
      case PlannerPhaseId.planning:
        return PlannerActionCode.startRetrieval;
      case PlannerPhaseId.executing:
        return PlannerActionCode.startRetrieval;
      case PlannerPhaseId.answering:
        return PlannerActionCode.composeAnswer;
      case PlannerPhaseId.completed:
        return PlannerActionCode.completeTurn;
      case PlannerPhaseId.understanding:
      default:
        return PlannerActionCode.frameProblem;
    }
  }

  static PlannerReasonCode _plannerReasonForNarrativePhase(
    PlannerPhaseId phase,
  ) {
    switch (phase) {
      case PlannerPhaseId.planning:
        return PlannerReasonCode.targetedProbe;
      case PlannerPhaseId.executing:
        return PlannerReasonCode.reduceWaitTime;
      case PlannerPhaseId.answering:
        return PlannerReasonCode.prepareDelivery;
      case PlannerPhaseId.completed:
        return PlannerReasonCode.readyToAnswer;
      case PlannerPhaseId.understanding:
      default:
        return PlannerReasonCode.alignGoal;
    }
  }

  static String _summarizeSubtask(Map<String, dynamic> data) {
    final summary = _sanitizeMessage(
      (data['summary'] as String?)?.trim() ?? '',
    );
    if (summary.isNotEmpty && !_looksTemplated(summary)) return summary;
    return '并行补充的这部分已经回来了，可以和主线信息一起判断了。';
  }

  static String _buildPlanStartedMessage(Map<String, dynamic> data) {
    final labels = _taskLabels(data);
    if (labels.length >= 2) {
      return '先把问题拆成${labels.take(3).join('、')}这几路，再决定从哪里查起。';
    }
    if (_isRealtimeProblemClass(data)) {
      final focus = _focusAnchor(data);
      if (focus.isNotEmpty) {
        return '先确认$focus的最新状态，再看哪些变化会直接影响判断。';
      }
      return '先确认当前状态，再看哪些变化会直接影响判断。';
    }
    final focus = _focusAnchor(data);
    if (focus.isNotEmpty) {
      return '先把“$focus”这条主线立住，后面的检索才不容易跑偏。';
    }
    return '先确认这次要优先解决哪一层，再决定从哪里查起。';
  }

  static String _buildThinkingStartedMessage(
    PlannerPhaseId stage,
    Map<String, dynamic> data,
  ) {
    switch (stage) {
      case PlannerPhaseId.analyzing:
        return '资料已经有一批了，先对齐一致和分歧，再继续收敛。';
      case PlannerPhaseId.answering:
        return '关键信息差不多齐了，开始整理成更容易使用的答案。';
      default:
        return '先把问题落点定清楚，后面的资料才更容易收敛。';
    }
  }

  static String _buildToolStartMessage(Map<String, dynamic> data) {
    final taskCount = _searchTaskCount(data);
    final labels = _taskLabels(data);
    final excluded = _negativeFocus(data);
    if (taskCount >= 2) {
      if (excluded.isNotEmpty) {
        return '我会按${labels.take(3).join('、')}几路分开核对，同时把“$excluded”相关的噪音结果筛掉。';
      }
      return '我会把问题拆成几个关键方向分开核对，这样更容易收敛，也更容易发现冲突。';
    }
    if (_isRealtimeProblemClass(data)) {
      final focus = _focusAnchor(data);
      if (focus.isNotEmpty) {
        return '先看$focus的当前状态，再补会直接影响判断的那层信息。';
      }
      return '先看当前状态，再补会直接影响判断的那层信息。';
    }
    final focus = _focusAnchor(data);
    if (focus.isNotEmpty) {
      return '先围绕“$focus”核对最影响判断的资料，确认主线站得住。';
    }
    return '先核对最影响判断的那层资料，确认主线站得住。';
  }

  static String _buildToolResultMessage(Map<String, dynamic> data, int refs) {
    final queryCount = _toPositiveInt(data['queryCount']) ?? 0;
    final labels = _stringList(data['queryLabels']);
    final covered = _stringList(data['coveredDimensions']);
    final missing = _stringList(data['missingDimensions']);
    if (refs > 0 && covered.isNotEmpty) {
      return '“${covered.take(2).join('、')}”这几路资料已经回来，我先交叉核对，再看还缺哪一块。';
    }
    if (queryCount >= 2 && refs > 0) {
      if (missing.isNotEmpty) {
        return '主线资料已经回来一批，我先交叉核对，再决定是否补“${missing.first}”这一块。';
      }
      return '这批资料已经回来，先交叉核对再判断还缺哪一块。';
    }
    if (refs > 0) {
      if (labels.isNotEmpty) {
        return '“${labels.first}”相关资料已经回来，我先判断哪些能直接支撑结论。';
      }
      return '这批资料已经回来，先交叉核对再判断哪些能直接支撑结论。';
    }
    return '资料已经回来，先判断哪些值得继续保留。';
  }

  static String _buildAssessmentMessage(Map<String, dynamic> data) {
    final assessment = _toolAssessmentFromData(data);
    final explicit = _sanitizeMessage(assessment.userMessage);
    if (explicit.isNotEmpty && !_looksTemplated(explicit)) {
      return explicit;
    }
    final refs = assessment.referenceCount;
    final queryCount = assessment.queryCount;
    switch (assessment.assessmentType) {
      case AssessmentType.needMoreSearch:
        if (!assessment.shouldContinueLoop) {
          return '我不再继续兜圈子了，直接基于已经确认的部分给你一个可用版本。';
        }
        return queryCount >= 2
            ? '主线已经有了，但还差一处会影响判断的信息，所以再补一轮。'
            : '还差一处会影响判断的信息，所以换个更具体的方向再补一轮。';
      case AssessmentType.toolFailed:
        return assessment.shouldContinueLoop
            ? '这一批外部资料不够稳，我换个来源继续。'
            : '这次没有拿到更稳的补充，所以只保留已经确认的部分。';
      case AssessmentType.budgetExhausted:
        return '已经有足够支撑判断的部分，先把最重要的结论整理出来。';
      case AssessmentType.sufficient:
        return refs > 0 || queryCount > 0
            ? '关键信息已经够用了，开始收拢成结论。'
            : '信息已经够用了，开始整理答案。';
      default:
        return _sanitizeMessage((data['userMessage'] as String?)?.trim() ?? '');
    }
  }

  static String _buildLifecycleEndMessage(Map<String, dynamic> data) {
    final outcome = (data['lifecycleOutcome'] as String?)?.trim() ?? '';
    final userMessage = _sanitizeMessage(
      (data['userMessage'] as String?)?.trim() ?? '',
    );
    if (outcome == 'completed') {
      return '关键信息已经收拢好了，下面我直接给你结论。';
    }
    if (outcome == 'degraded') {
      return '我没再等更多不稳的信息，接下来直接给你已经确认的内容。';
    }
    if (userMessage.isNotEmpty && !_looksTemplated(userMessage)) return userMessage;
    return '';
  }

  static String _buildToolErrorMessage(
    Map<String, dynamic> data,
    String fallbackMessage,
  ) {
    if (data['retrievalLike'] == true) {
      return '这一批资料暂时不够稳，马上换个来源继续。';
    }
    final sanitized = _sanitizeMessage(fallbackMessage);
    if (sanitized.isNotEmpty && !_looksTemplated(sanitized)) return sanitized;
    return '这一步有点不顺，我马上换个办法继续。';
  }

  static String _buildThinkingProgressMessage(
    PlannerPhaseId stage,
    Map<String, dynamic> data,
  ) {
    final explicit = _sanitizeMessage(
      (data['reasonShort'] as String?)?.trim() ?? '',
    );
    if (explicit.isNotEmpty && !_looksTemplated(explicit)) {
      return explicit;
    }
    switch (stage) {
      case PlannerPhaseId.analyzing:
        return '我在把几路信息放到一起对照，先看哪些能直接支撑结论。';
      case PlannerPhaseId.answering:
        return '我在把已经确认的部分整理成更容易使用的答案。';
      default:
        return '我在确认问题边界，避免后面越查越散。';
    }
  }

  static PlannerPhaseId _resolveThinkingStage(Map<String, dynamic> data) {
    final phase = (data['phase'] as String?)?.trim().toLowerCase() ?? '';
    if (phase == PlannerPhaseId.analyzing.wireName ||
        phase == PlannerPhaseId.answering.wireName) {
      return parsePlannerPhaseId(phase);
    }
    final iteration = (data['iteration'] as num?)?.toInt() ?? 1;
    return iteration > 1
        ? PlannerPhaseId.analyzing
        : PlannerPhaseId.understanding;
  }

  static UserEventScope _scopeForStage(PlannerPhaseId stage) {
    return stage == PlannerPhaseId.understanding
        ? UserEventScope.root
        : UserEventScope.aggregation;
  }

  static String _nodeIdForStage(PlannerPhaseId stage) {
    switch (stage) {
      case PlannerPhaseId.analyzing:
        return 'aggregation.analysis';
      case PlannerPhaseId.answering:
        return 'aggregation.answer';
      default:
        return 'root.intent';
    }
  }

  static String _searchNodeId(String toolName) {
    return toolName.isEmpty ? 'skill.search' : 'skill.$toolName';
  }

  static String _thinkingIntroNodeId(PlannerPhaseId stage) {
    return '${_nodeIdForStage(stage)}.intro';
  }

  static String _thinkingStreamNodeId(PlannerPhaseId stage) {
    return '${_nodeIdForStage(stage)}.stream';
  }

  static String _searchPlanNodeId(String toolName) {
    return '${_searchNodeId(toolName)}.plan';
  }

  static String _searchResultNodeId(String toolName) {
    return '${_searchNodeId(toolName)}.result';
  }

  static String _subagentPlanNodeId(Map<String, dynamic> data) {
    final domainId = (data['domainId'] as String?)?.trim() ?? 'skill.secondary';
    return '$domainId.plan';
  }

  static String _subagentResultNodeId(Map<String, dynamic> data) {
    final domainId = (data['domainId'] as String?)?.trim() ?? 'skill.secondary';
    return '$domainId.result';
  }

  static String _buildSubagentStartMessage() {
    return '我并行补另一块关键信息，这样整体收得更快。';
  }

  static int _searchTaskCount(Map<String, dynamic> data) {
    final tasks = (data['queryTasks'] as List?)?.length ?? 0;
    if (tasks > 0) return tasks;
    final variants = (data['queryVariants'] as List?)?.length ?? 0;
    if (variants > 0) return variants;
    final queryCount = _toPositiveInt(data['queryCount']);
    if (queryCount != null) return queryCount;
    return 0;
  }

  static PlannerReasonCode _assessmentReasonCode(Map<String, dynamic> data) {
    final assessment = _toolAssessmentFromData(data);
    if (assessment.reasonCode != PlannerReasonCode.unknownReason) {
      return assessment.reasonCode;
    }
    switch (assessment.assessmentType) {
      case AssessmentType.needMoreSearch:
        return PlannerReasonCode.needMoreEvidence;
      case AssessmentType.toolFailed:
        return PlannerReasonCode.sourceUnstable;
      case AssessmentType.budgetExhausted:
        return PlannerReasonCode.budgetBoundary;
      case AssessmentType.sufficient:
        return PlannerReasonCode.evidenceReady;
      default:
        return PlannerReasonCode.assessmentUpdate;
    }
  }

  static ToolAssessment _toolAssessmentFromData(Map<String, dynamic> data) {
    final raw =
        (data['assessment'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{
          'assessmentType': (data['assessmentType'] as String?)?.trim() ?? '',
          'userMessage': (data['userMessage'] as String?)?.trim() ?? '',
          'shouldContinueLoop': data['shouldContinueLoop'] == true,
          'reasonCode': (data['reasonCode'] as String?)?.trim() ?? '',
          'referenceCount': _toPositiveInt(data['referenceCount']) ?? 0,
          'queryCount': _toPositiveInt(data['queryCount']) ?? 0,
          'coveredDimensions': data['coveredDimensions'],
          'missingDimensions': data['missingDimensions'],
        };
    return ToolAssessment.fromJson(raw);
  }

  static int? _toPositiveInt(Object? value) {
    if (value is num) {
      final number = value.toInt();
      return number > 0 ? number : null;
    }
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed == null || parsed <= 0) return null;
    return parsed;
  }

  static bool _isRealtimeProblemClass(Map<String, dynamic> data) {
    final raw = (data['problemClass'] as String?)?.trim() ?? '';
    return parseProblemClass(raw) == ProblemClass.realtimeInfo;
  }

  static List<String> _taskLabels(Map<String, dynamic> data) {
    return (data['queryTasks'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .map(
              (item) =>
                  (item['label'] as String?)?.trim() ??
                  (item['dimension'] as String?)?.trim() ??
                  '',
            )
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
  }

  static List<String> _stringList(Object? raw) {
    return (raw as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
  }

  static String _focusAnchor(Map<String, dynamic> data) {
    final normalization =
        (data['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final anchors = _stringList(
      normalization['entityAnchors'] ?? data['entityAnchors'],
    );
    if (anchors.isNotEmpty) return anchors.first;
    return '';
  }

  static String _negativeFocus(Map<String, dynamic> data) {
    final normalization =
        (data['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final negatives = _stringList(
      normalization['negativeKeywords'] ??
          normalization['excludedScopes'] ??
          data['negativeKeywords'],
    );
    return negatives.isEmpty ? '' : negatives.take(2).join('、');
  }

  static String _sanitizeMessage(String raw) {
    var text = raw.trim();
    if (text.isEmpty) return '';
    const blockedFragments = <String>[
      'queryTasks',
      'queryVariants',
      'freshnessHoursMax',
      'provider',
      'contractVersion',
      'assistant_turn',
      'tool_call',
      '<tool_call>',
      '</tool_call>',
      'timeScope',
      'machineEnvelope',
      'runArtifacts',
    ];
    for (final fragment in blockedFragments) {
      if (text.contains(fragment)) return '';
    }
    if (text.startsWith('{') || text.startsWith('[')) return '';
    return text;
  }

  static bool _looksTemplated(String text) {
    return text.contains('我先帮你把') ||
        text.contains('我先把') ||
        text.contains('收一收') ||
        text.contains('你更像是想知道') ||
        text.contains('我先替你');
  }
}
