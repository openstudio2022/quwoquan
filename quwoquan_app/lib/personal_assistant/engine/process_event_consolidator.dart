import 'package:quwoquan_app/personal_assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

/// Stateful consolidator that converts raw [AssistantTraceEvent]s into
/// deduplicated, user-language [ExplainableFlowEvent]s.
///
/// Replaces the previous three parallel translation paths:
///   - `_emitSemanticEvent`   → `UserPhaseEventType`
///   - `_emitUserEvent`       → `UserEvent`
///   - `processUpdate`        → `AssistantProcessState`
class ProcessEventConsolidator {
  ProcessEventConsolidator({
    this.problemClass = 'general',
    this.userGoalSummary = '',
    this.multiAgent = false,
  }) {
    _visiblePhases = PhaseVisibility.forProblemClass(
      problemClass,
      multiAgent: multiAgent,
    );
  }

  final String problemClass;
  final String userGoalSummary;
  final bool multiAgent;

  late final List<String> _visiblePhases;

  final List<ExplainableFlowEvent> _emittedEvents = <ExplainableFlowEvent>[];
  final Set<String> _seenReferenceUrls = <String>{};
  int _lastEmittedRefCount = 0;
  String _currentPhaseId = '';
  int _phaseCounter = 0;

  /// All events emitted so far (for persistence / drawer rebuild).
  List<ExplainableFlowEvent> get snapshot =>
      List<ExplainableFlowEvent>.unmodifiable(_emittedEvents);

  /// Whether the answer gate is open (aggregate completed).
  bool get answerGateOpen {
    return _emittedEvents.any(
      (e) =>
          (e.phaseId == PhaseId.aggregate || e.phaseId == PhaseId.merge) &&
          e.phaseStatus == ExplainablePhaseStatus.completed,
    );
  }

  /// Process a raw trace event and optionally emit an [ExplainableFlowEvent].
  ExplainableFlowEvent? consolidate(AssistantTraceEvent event) {
    if (!event.visibility.isUserVisible) return null;
    switch (event.type) {
      case AssistantTraceEventType.planStarted:
        return _emitPhase(
          phaseId: _firstVisiblePhase(),
          headline: _buildUnderstandHeadline(event),
        );

      case AssistantTraceEventType.thinkingStarted:
        final iteration = (event.data?['iteration'] as int?) ?? 1;
        if (iteration > 1) {
          return _emitPhase(
            phaseId: _resolveAnalyzingPhase(),
            headline: '我先把拿到的资料对一遍，看看哪些已经能直接支撑结论。',
          );
        }
        return _updateCurrentHeadline('先把问题落点理清楚，后面的资料才更容易收敛。');

      case AssistantTraceEventType.thinkingProgress:
        final phase = (event.data?['phase'] as String?) ?? '';
        if (phase == 'answering') {
          return _emitPhase(
            phaseId: PhaseId.answer,
            headline: '我在组织最终回答',
          );
        }
        final cleaned = _sanitizeForUser(
          (event.data?['reasonShort'] as String?)?.trim() ?? '',
        );
        if (cleaned.isNotEmpty) {
          return _updateCurrentHeadline(cleaned);
        }
        return _updateCurrentHeadline(_defaultProgressHeadline(phase));

      case AssistantTraceEventType.toolStart:
        final toolName = _extractToolName(event.data);
        if (!toolName.contains('search') && !toolName.contains('fetch')) {
          return null;
        }
        return _emitPhase(
          phaseId: PhaseId.execute,
          headline: _buildSearchStartHeadline(event),
        );

      case AssistantTraceEventType.toolResult:
        if (event.data?['isAssessment'] == true) {
          return _handleAssessment(event);
        }
        return _handleToolResult(event);

      case AssistantTraceEventType.toolError:
        return _updateCurrentHeadline('这一批资料暂时没拿稳，我换个方式继续替你核。');

      case AssistantTraceEventType.subagentStart:
        return _handleSubagentStart(event);

      case AssistantTraceEventType.subagentResult:
        return _handleSubagentResult(event);

      case AssistantTraceEventType.subagentError:
        return _handleSubagentError(event);

      case AssistantTraceEventType.replanTriggered:
        if (problemClass == 'realtime_info') return null;
        return _emitPhase(
          phaseId: PhaseId.expand,
          headline: '还差一处会影响判断的信息，我再补一轮。',
        );

      case AssistantTraceEventType.lifecycleEnd:
        if (event.message.contains('finished')) {
          _completeCurrentPhase();
          if (!answerGateOpen && _currentPhaseId != PhaseId.answer) {
            return _emitPhase(
              phaseId: PhaseId.answer,
              headline: '已为你整理好',
              status: ExplainablePhaseStatus.completed,
            );
          }
        }
        return null;

      default:
        return null;
    }
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  String _firstVisiblePhase() {
    return _visiblePhases.isNotEmpty ? _visiblePhases.first : PhaseId.understand;
  }

  String _resolveAnalyzingPhase() {
    if (_visiblePhases.contains(PhaseId.aggregate)) return PhaseId.aggregate;
    if (_visiblePhases.contains(PhaseId.execute)) return PhaseId.execute;
    return PhaseId.understand;
  }

  ExplainableFlowEvent? _emitPhase({
    required String phaseId,
    required String headline,
    String detail = '',
    String agentId = 'main',
    String parentPhaseId = '',
    List<FlowReference> references = const <FlowReference>[],
    ExplainablePhaseStatus status = ExplainablePhaseStatus.active,
  }) {
    if (!_visiblePhases.contains(phaseId) &&
        phaseId != PhaseId.subExecute &&
        phaseId != PhaseId.expand) {
      return null;
    }

    _completeCurrentPhase();
    _currentPhaseId = phaseId;

    final event = ExplainableFlowEvent(
      phaseId: phaseId,
      phaseOrder: _phaseCounter++,
      phaseStatus: status,
      headline: headline,
      detail: detail,
      agentId: agentId,
      parentPhaseId: parentPhaseId,
      references: references,
    );
    _emittedEvents.add(event);
    return event;
  }

  void _completeCurrentPhase() {
    if (_currentPhaseId.isEmpty || _emittedEvents.isEmpty) return;
    final lastIndex = _emittedEvents.lastIndexWhere(
      (e) =>
          e.phaseId == _currentPhaseId &&
          e.phaseStatus == ExplainablePhaseStatus.active,
    );
    if (lastIndex < 0) return;
    _emittedEvents[lastIndex] = _emittedEvents[lastIndex].copyWith(
      phaseStatus: ExplainablePhaseStatus.completed,
    );
  }

  ExplainableFlowEvent? _updateCurrentHeadline(String headline) {
    if (_emittedEvents.isEmpty) return null;
    final last = _emittedEvents.last;
    if (last.phaseStatus != ExplainablePhaseStatus.active) return null;
    final updated = last.copyWith(headline: headline);
    _emittedEvents[_emittedEvents.length - 1] = updated;
    return updated;
  }

  ExplainableFlowEvent? _updateCurrentDetail(String detail) {
    if (_emittedEvents.isEmpty) return null;
    final last = _emittedEvents.last;
    if (last.phaseStatus != ExplainablePhaseStatus.active) return null;
    final updated = last.copyWith(detail: detail);
    _emittedEvents[_emittedEvents.length - 1] = updated;
    return updated;
  }

  ExplainableFlowEvent? _handleAssessment(AssistantTraceEvent event) {
    final assessmentType =
        (event.data?['assessmentType'] as String?)?.trim().toLowerCase() ?? '';
    switch (assessmentType) {
      case 'sufficient':
        final refs = (event.data?['references'] as List?)?.length ?? 0;
        if (refs > 0 && refs != _lastEmittedRefCount) {
          _lastEmittedRefCount = refs;
          return _updateCurrentHeadline('关键信息已经够用了，我开始把这 $refs 条线索收拢成你能直接参考的结论。');
        }
        return _updateCurrentHeadline('关键信息已经够用了，我开始整理答案。');
      case 'budgetexhausted':
        return _updateCurrentHeadline('已经有一批能支撑判断的信息了，我先把最重要的部分整理给你。');
      case 'needmoresearch':
        if (problemClass == 'realtime_info') return null;
        return _updateCurrentHeadline('目前主线已经有了，但还差一处关键信息，我再替你补一下。');
      case 'toolfailed':
        return _updateCurrentHeadline('这轮外部资料不太稳，我先基于已经确认的部分替你整理。');
      default:
        return null;
    }
  }

  ExplainableFlowEvent? _handleToolResult(AssistantTraceEvent event) {
    final refs = (event.data?['references'] as List?) ?? const <dynamic>[];
    final refCount = refs.length;
    if (refCount == 0) return null;
    if (refCount == _lastEmittedRefCount) return null;
    _lastEmittedRefCount = refCount;

    final flowRefs = <FlowReference>[];
    for (final item in refs) {
      if (item is! Map) continue;
      final m = item.cast<String, dynamic>();
      final title = (m['title'] as String?)?.trim() ?? '';
      final url = (m['url'] as String?)?.trim() ?? '';
      if (title.isEmpty || url.isEmpty) continue;
      if (_seenReferenceUrls.contains(url)) continue;
      _seenReferenceUrls.add(url);
      flowRefs.add(FlowReference(
        title: title,
        url: url,
        source: (m['source'] as String?)?.trim() ?? '',
      ));
    }

    if (_emittedEvents.isEmpty) return null;
    final last = _emittedEvents.last;
    final updatedRefs = <FlowReference>[...last.references, ...flowRefs];
    final totalCount = updatedRefs.length;
    final updated = last.copyWith(
      headline: '这一批资料已经回来了，我先从 $totalCount 个来源里筛掉重复和噪音。',
      references: updatedRefs,
    );
    _emittedEvents[_emittedEvents.length - 1] = updated;
    return updated;
  }

  ExplainableFlowEvent? _handleSubagentStart(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    final domainId = (data['domainId'] as String?)?.trim() ?? '';
    return _emitPhase(
      phaseId: PhaseId.subExecute,
      headline: '我并行补另一部分信息，尽量一起收拢。',
      agentId: (data['subagentId'] as String?)?.trim() ?? domainId,
      parentPhaseId: PhaseId.dispatch,
    );
  }

  ExplainableFlowEvent? _handleSubagentResult(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    final summary = _sanitizeForUser(
      (data['summary'] as String?)?.trim() ?? '',
    );
    _completeCurrentPhase();
    if (summary.isNotEmpty && _emittedEvents.isNotEmpty) {
      final last = _emittedEvents.last;
      _emittedEvents[_emittedEvents.length - 1] = last.copyWith(
        headline: summary,
        phaseStatus: ExplainablePhaseStatus.completed,
      );
      return _emittedEvents.last;
    }
    return null;
  }

  ExplainableFlowEvent? _handleSubagentError(AssistantTraceEvent event) {
    _completeCurrentPhase();
    if (_emittedEvents.isNotEmpty) {
      final last = _emittedEvents.last;
      _emittedEvents[_emittedEvents.length - 1] = last.copyWith(
        headline: '这一部分暂时还不够完整，我先用已经确认的内容继续替你整理。',
        phaseStatus: ExplainablePhaseStatus.failed,
      );
      return _emittedEvents.last;
    }
    return null;
  }

  String _buildUnderstandHeadline(AssistantTraceEvent event) {
    final goal = _sanitizeForUser(
      (event.data?['goal'] as String?)?.trim() ?? '',
    );
    if (_isWeatherLike(goal)) {
      final city = _extractCity(goal);
      if (city.isNotEmpty) {
        return '先确认$city的实时情况，再补对出行最有用的提醒。';
      }
      return '先确认实时情况，再补对出行最有用的提醒。';
    }
    return '先确认这次要优先解决哪一层，再决定从哪里查起。';
  }

  String _buildSearchStartHeadline(AssistantTraceEvent event) {
    if (_isWeatherLike(userGoalSummary)) {
      final city = _extractCity(userGoalSummary);
      if (city.isNotEmpty) return '先看$city的实时情况，再补出门最相关的提醒。';
      return '先看实时情况，再补出门最相关的提醒。';
    }
    return '先核对最影响结论的资料，尽量少带回无关信息。';
  }

  String _defaultProgressHeadline(String phase) {
    switch (phase) {
      case 'analyzing':
        return '我在把几路信息放到一起对照，先看哪些能直接支撑结论。';
      case 'searching':
        return '我在核对关键资料，先把会影响判断的部分查稳。';
      default:
        return '我在确认问题边界，避免后面越查越散。';
    }
  }

  // ---------------------------------------------------------------------------
  // Text utilities
  // ---------------------------------------------------------------------------

  static final _blockedFragments = <String>[
    'queryVariants',
    'freshnessHoursMax',
    'provider',
    'contractVersion',
    'assistant_turn_v4',
    'tool_call',
    '<tool_call>',
    '</tool_call>',
    'timeScope',
  ];

  String _sanitizeForUser(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return '';
    for (final f in _blockedFragments) {
      if (text.contains(f)) return '';
    }
    if (text.startsWith('{') || text.startsWith('[')) return '';
    return text;
  }

  String _humanizeForUser(String raw) {
    final text = _sanitizeForUser(raw);
    if (text.isEmpty) return '';
    if (text.contains('我先帮你把') ||
        text.contains('收一收') ||
        text.contains('你更像是想知道') ||
        text.contains('我先替你')) {
      return '';
    }
    return text;
  }

  static bool _isWeatherLike(String text) {
    if (text.isEmpty) return false;
    return RegExp(
      r'(天气|气温|降雨|风力|体感|预报|weather|forecast|temperature|humidity|rain)',
      caseSensitive: false,
    ).hasMatch(text);
  }

  static String _extractCity(String text) {
    if (text.isEmpty) return '';
    return RegExp(r'([\u4e00-\u9fa5]{2,8}(?:市|区|县)|[\u4e00-\u9fa5]{2,8})')
            .firstMatch(text)
            ?.group(1)
            ?.trim() ??
        '';
  }

  static String _extractToolName(Map<String, dynamic>? data) {
    if (data == null) return '';
    return (data['toolName'] ?? data['tool'] ?? data['stepId'] ?? '')
        .toString()
        .split('_')
        .first
        .trim()
        .toLowerCase();
  }
}
