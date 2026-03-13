import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

class TraceUserEventTranslator {
  static UserEvent? translate(AssistantTraceEvent event) {
    if (!event.visibility.isUserVisible) return null;
    final data = event.data ?? const <String, dynamic>{};
    switch (event.type) {
      case AssistantTraceEventType.planStarted:
        final phaseId = 'understanding';
        final isWeather = _isWeatherLikeText(
          _sanitizeMessage((data['goal'] as String?)?.trim() ?? ''),
        );
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.root,
          nodeId: 'root.intent.plan',
          runId: event.runId ?? '',
          phaseId: phaseId,
          actionCode: 'frame_problem',
          reasonCode: isWeather ? 'confirm_realtime_scope' : 'align_goal',
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
          actionCode: stage == 'answering'
              ? 'compose_answer'
              : 'align_evidence',
          reasonCode: stage == 'analyzing'
              ? 'check_consistency'
              : stage == 'answering'
              ? 'prepare_delivery'
              : 'confirm_focus',
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
          actionCode: stage == 'answering'
              ? 'compose_answer'
              : 'align_evidence',
          reasonCode: stage == 'analyzing'
              ? 'check_consistency'
              : stage == 'answering'
              ? 'prepare_delivery'
              : 'confirm_focus',
          reasonShort: message,
          extraPayload: <String, dynamic>{if (isStreaming) 'streaming': true},
        );
      case AssistantTraceEventType.toolStart:
        if (_isSearchLike(event, data)) {
          final toolName = _toolName(data);
          return _buildEvent(
            type: UserEventType.processCommit,
            scope: UserEventScope.skill,
            nodeId: _searchPlanNodeId(toolName),
            runId: event.runId ?? '',
            phaseId: 'searching',
            actionCode: 'start_retrieval',
            reasonCode: _searchTaskCount(data) > 1
                ? 'parallel_probe'
                : 'targeted_probe',
            reasonShort: _buildToolStartMessage(data),
            extraPayload: <String, dynamic>{
              'toolName': toolName,
              if (data['queryTasks'] is List)
                'queryTaskCount': _searchTaskCount(data),
            },
          );
        }
        return null;
      case AssistantTraceEventType.toolResult:
        if (data['isAssessment'] == true) {
          final userMessage = _buildAssessmentMessage(data);
          if (userMessage.isEmpty) return null;
          return _buildEvent(
            type: UserEventType.processAppend,
            scope: UserEventScope.aggregation,
            nodeId: 'aggregation.assessment',
            runId: event.runId ?? '',
            phaseId: 'analyzing',
            actionCode: 'assess_evidence',
            reasonCode: _assessmentReasonCode(data),
            reasonShort: userMessage,
          );
        }
        final refs = (data['references'] as List?)?.length ?? 0;
        if (refs > 0) {
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
            phaseId: 'searching',
            actionCode: 'review_sources',
            reasonCode: refs >= 3 ? 'cross_check_sources' : 'validate_source',
            reasonShort: _buildToolResultMessage(data, refs),
            extraPayload: <String, dynamic>{
              'referenceCount': refs,
              'references': references,
            },
          );
        }
        return null;
      case AssistantTraceEventType.toolError:
        return _buildEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: _searchResultNodeId(_toolName(data)),
          runId: event.runId ?? '',
          phaseId: 'searching',
          actionCode: 'recover_retrieval',
          reasonCode: 'source_unstable',
          reasonShort: _buildToolErrorMessage(data, event.message),
        );
      case AssistantTraceEventType.subagentStart:
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: _subagentPlanNodeId(data),
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          phaseId: 'searching',
          actionCode: 'parallel_probe',
          reasonCode: 'reduce_wait_time',
          reasonShort: _buildSubagentStartMessage(),
        );
      case AssistantTraceEventType.subagentResult:
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: _subagentResultNodeId(data),
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          phaseId: 'analyzing',
          actionCode: 'merge_parallel_result',
          reasonCode: 'evidence_back',
          reasonShort: _summarizeSubtask(data),
        );
      case AssistantTraceEventType.subagentError:
        return _buildEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: _subagentResultNodeId(data),
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          phaseId: 'analyzing',
          actionCode: 'fallback_with_existing_evidence',
          reasonCode: 'parallel_branch_failed',
          reasonShort: '并行补充的这一支还不够稳，我继续用已经确认的部分往下收敛。',
        );
      case AssistantTraceEventType.lifecycleEnd:
        final userMessage = _buildLifecycleEndMessage(data);
        if (userMessage.isEmpty) return null;
        return _buildEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.aggregation,
          nodeId: 'aggregation.final',
          runId: event.runId ?? '',
          phaseId: 'completed',
          actionCode: 'complete_turn',
          reasonCode: 'ready_to_answer',
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
    required String phaseId,
    required String actionCode,
    required String reasonCode,
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
        'stage': phaseId,
        'phaseId': phaseId,
        'actionCode': actionCode,
        'reasonCode': reasonCode,
        'reasonShort': reasonShort,
        'source': 'trace_translator',
        ...extraPayload,
      },
    );
  }

  static bool _isSearchLike(
    AssistantTraceEvent event,
    Map<String, dynamic> data,
  ) {
    final toolName = _toolName(data).toLowerCase();
    if (toolName.contains('search') || toolName.contains('fetch')) {
      return true;
    }
    return event.message.toLowerCase().contains('search');
  }

  static String _toolName(Map<String, dynamic> data) {
    return (data['toolName'] ?? data['tool'] ?? data['stepId'] ?? '')
        .toString()
        .split('_')
        .first
        .trim();
  }

  static String _summarizeSubtask(Map<String, dynamic> data) {
    final summary = _sanitizeMessage(
      (data['summary'] as String?)?.trim() ?? '',
    );
    if (summary.isNotEmpty && !_looksTemplated(summary)) return summary;
    return '并行补充的这部分已经回来了，可以和主线信息一起判断了。';
  }

  static String _buildPlanStartedMessage(Map<String, dynamic> data) {
    final goal = _sanitizeMessage((data['goal'] as String?)?.trim() ?? '');
    if (_isWeatherLikeText(goal)) {
      final city = _extractCity(goal);
      if (city.isNotEmpty) {
        return '先确认$city的实时情况，再补对出行最有用的提醒。';
      }
      return '先确认实时情况，再补对出行最有用的提醒。';
    }
    return '先确认这次要优先解决哪一层，再决定从哪里查起。';
  }

  static String _buildThinkingStartedMessage(
    String stage,
    Map<String, dynamic> data,
  ) {
    switch (stage) {
      case 'analyzing':
        return '资料已经有一批了，先对齐一致和分歧，再继续收敛。';
      case 'answering':
        return '关键信息差不多齐了，开始整理成更容易使用的答案。';
      default:
        return '先把问题落点定清楚，后面的资料才更容易收敛。';
    }
  }

  static String _buildToolStartMessage(Map<String, dynamic> data) {
    final taskCount = _searchTaskCount(data);
    final labels =
        (data['queryTasks'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .map((item) => (item['label'] as String?)?.trim() ?? '')
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (labels.contains('候选路线') && labels.contains('适用条件')) {
      return '我把九寨沟方向拆成候选路线、适用条件和关键取舍三块并行核对，先把真正影响选择的差别拎出来。';
    }
    if (labels.contains('季节窗口') &&
        labels.contains('日内时段') &&
        labels.contains('天气条件')) {
      return '我把观赏时间拆成季节、一天中的时段和天气条件三块并行核对，这样后面可以直接给到结论。';
    }
    if (taskCount >= 2) {
      return '我会把问题拆成几个关键方向分开核对，这样更容易收敛，也更容易发现冲突。';
    }
    final query = _sanitizeMessage((data['query'] as String?)?.trim() ?? '');
    if (_isWeatherLikeText(query)) {
      final city = _extractCity(query);
      if (city.isNotEmpty) {
        return '先看$city的实时情况，再补会直接影响判断的提醒。';
      }
      return '先看实时情况，再补会直接影响判断的提醒。';
    }
    return '先核对最影响判断的那层资料，确认主线站得住。';
  }

  static String _buildToolResultMessage(Map<String, dynamic> data, int refs) {
    final queryCount = _toPositiveInt(data['queryCount']) ?? 0;
    final labels =
        (data['queryLabels'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (labels.contains('候选路线') && refs > 0) {
      return '几路候选资料已经回来，我先对照哪些方案更值得放进最终备选。';
    }
    if (labels.contains('季节窗口') && refs > 0) {
      return '季节、时段和天气这几路资料已经回来，我先交叉核对是否能直接给出观赏建议。';
    }
    if (queryCount >= 2 && refs > 0) {
      return '这批资料已经回来，先交叉核对再判断还缺哪一块。';
    }
    if (refs > 0) {
      return '这批资料已经回来，先交叉核对再判断哪些能直接支撑结论。';
    }
    return '资料已经回来，先判断哪些值得继续保留。';
  }

  static String _buildAssessmentMessage(Map<String, dynamic> data) {
    final assessmentType =
        (data['assessmentType'] as String?)?.trim().toLowerCase() ?? '';
    final shouldContinue = data['shouldContinueLoop'] == true;
    final refs =
        _toPositiveInt(data['referenceCount']) ??
        (data['references'] as List?)?.length ??
        0;
    final queryCount = _toPositiveInt(data['queryCount']) ?? 0;
    switch (assessmentType) {
      case 'needMoreSearch':
        if (!shouldContinue) {
          return '我不再继续兜圈子了，直接基于已经确认的部分给你一个可用版本。';
        }
        return queryCount >= 2
            ? '主线已经有了，但还差一处会影响判断的信息，所以再补一轮。'
            : '还差一处会影响判断的信息，所以换个更具体的方向再补一轮。';
      case 'toolFailed':
        return shouldContinue
            ? '这一批外部资料不够稳，我换个来源继续。'
            : '这次没有拿到更稳的补充，所以只保留已经确认的部分。';
      case 'budgetExhausted':
        return '已经有足够支撑判断的部分，先把最重要的结论整理出来。';
      case 'sufficient':
        return refs > 0 || queryCount > 0
            ? '关键信息已经够用了，开始收拢成结论。'
            : '信息已经够用了，开始整理答案。';
      default:
        return _sanitizeMessage((data['userMessage'] as String?)?.trim() ?? '');
    }
  }

  static String _buildLifecycleEndMessage(Map<String, dynamic> data) {
    final userMessage = _sanitizeMessage(
      (data['userMessage'] as String?)?.trim() ?? '',
    );
    if (userMessage.isNotEmpty) {
      if (userMessage.contains('基于已有信息') ||
          userMessage.contains('已有知识') ||
          userMessage.contains('遇到困难')) {
        return '我没再等更多不稳的信息，接下来直接给你已经确认的内容。';
      }
      if (userMessage.contains('完成')) {
        return '关键信息已经收拢好了，下面我直接给你结论。';
      }
      if (!_looksTemplated(userMessage)) return userMessage;
    }
    return '关键信息已经收拢好了，下面直接给你结论。';
  }

  static String _buildToolErrorMessage(
    Map<String, dynamic> data,
    String fallbackMessage,
  ) {
    final toolName = _toolName(data);
    if (toolName.contains('search') || toolName.contains('fetch')) {
      return '这一批资料暂时不够稳，马上换个来源继续。';
    }
    final sanitized = _sanitizeMessage(fallbackMessage);
    if (sanitized.isNotEmpty && !_looksTemplated(sanitized)) return sanitized;
    return '这一步有点不顺，我马上换个办法继续。';
  }

  static String _buildThinkingProgressMessage(
    String stage,
    Map<String, dynamic> data,
  ) {
    final explicit = _sanitizeMessage(
      (data['reasonShort'] as String?)?.trim() ?? '',
    );
    if (explicit.isNotEmpty && !_looksTemplated(explicit)) {
      return explicit;
    }
    switch (stage) {
      case 'analyzing':
        return '我在把几路信息放到一起对照，先看哪些能直接支撑结论。';
      case 'answering':
        return '我在把已经确认的部分整理成更容易使用的答案。';
      default:
        return '我在确认问题边界，避免后面越查越散。';
    }
  }

  static String _resolveThinkingStage(Map<String, dynamic> data) {
    final phase = (data['phase'] as String?)?.trim().toLowerCase() ?? '';
    if (phase == 'analyzing' || phase == 'answering') return phase;
    final iteration = (data['iteration'] as num?)?.toInt() ?? 1;
    return iteration > 1 ? 'analyzing' : 'understanding';
  }

  static UserEventScope _scopeForStage(String stage) {
    return stage == 'understanding'
        ? UserEventScope.root
        : UserEventScope.aggregation;
  }

  static String _nodeIdForStage(String stage) {
    switch (stage) {
      case 'analyzing':
        return 'aggregation.analysis';
      case 'answering':
        return 'aggregation.answer';
      default:
        return 'root.intent';
    }
  }

  static String _searchNodeId(String toolName) {
    return toolName.isEmpty ? 'skill.search' : 'skill.$toolName';
  }

  static String _thinkingIntroNodeId(String stage) {
    return '${_nodeIdForStage(stage)}.intro';
  }

  static String _thinkingStreamNodeId(String stage) {
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

  static String _assessmentReasonCode(Map<String, dynamic> data) {
    final raw = (data['assessmentType'] as String?)?.trim().toLowerCase() ?? '';
    switch (raw) {
      case 'needmoresearch':
        return 'need_more_evidence';
      case 'toolfailed':
        return 'source_unstable';
      case 'budgetexhausted':
        return 'budget_boundary';
      case 'sufficient':
        return 'evidence_ready';
      default:
        return 'assessment_update';
    }
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

  static String _compactText(String text, {int maxLength = 20}) {
    final normalized = text.trim();
    if (normalized.length <= maxLength) return normalized;
    return '${normalized.substring(0, maxLength)}...';
  }

  static bool _isWeatherLikeText(String text) {
    if (text.isEmpty) return false;
    return RegExp(
      r'(天气|气温|降雨|风力|体感|预报|weather|forecast|temperature|humidity|rain)',
      caseSensitive: false,
    ).hasMatch(text);
  }

  static String _extractCity(String text) {
    if (text.isEmpty) return '';
    return RegExp(
          r'([\u4e00-\u9fa5]{2,8}(?:市|区|县|沟|山|湖|草原|景区|国家公园))',
        ).firstMatch(text)?.group(1)?.trim() ??
        '';
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
      'assistant_turn_v4',
      'tool_call',
      '<tool_call>',
      '</tool_call>',
      'timeScope',
      'machineEnvelope',
      'runArtifactsV1',
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
