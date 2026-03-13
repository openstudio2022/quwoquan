import 'aggregation_state.dart';
import 'intent_graph.dart';
import 'preference_fact.dart';
import 'run_artifacts.dart';
import 'skill_run.dart';
import 'subagent_plan.dart';
import 'ui_process_timeline_entry.dart';
import 'user_events.dart';

// ─────────────────────────────────────────────────────────────────────────────
// AssistantTurn 输出契约
//
// 版本管理规则（见 02-dart-coding §5.3）：
//   - 当前版本：kAssistantTurnCurrentVersion（prompt 模板输出，所有新写入使用此值）
//   - 遗留版本：kAssistantTurnLegacyVersion（读取旧历史数据时兼容，session 加载后迁移）
//   - 旧包裹 key：kAssistantTurnV2WrapKey（仅用于解包，不作为 contractVersion 写入）
//   - 禁止同时存在三个及以上活跃版本（见 §5.3）
//
// 字段访问规则（见 02-dart-coding §5.1）：
//   - 字段名字符串字面量只允许出现在本文件的 tryParse() 方法内
//   - 引擎逻辑代码必须通过 AssistantTurnOutput 类型化属性访问，禁止直接写 map['fieldName']
// ─────────────────────────────────────────────────────────────────────────────

/// 当前规范版本（prompt 模板输出此值，所有新写入使用此常量）。
const String kAssistantTurnCurrentVersion = 'assistant_turn_v4';

/// 兼容遗留版本（加载旧 session 历史时识别，读后应升级到当前版本）。
const String kAssistantTurnLegacyVersion = 'assistant_turn_v3';

/// 旧包裹格式 key（仅用于从旧格式 `{ "assistant_turn_v2": {...} }` 解包）。
/// 禁止将此值作为 contractVersion 写入任何新数据。
const String kAssistantTurnV2WrapKey = 'assistant_turn_v2';

// ─────────────────────────────────────────────────────────────────────────────

enum AssistantNextAction { toolCall, answer, askUser, retry, abort, unknown }

enum AssistantMessageKind {
  progress,
  answer,
  askUser,
  error,
  fallback,
  unknown,
}

// ─────────────────────────────────────────────────────────────────────────────

/// LLM 输出契约（assistant_turn_v4）的完整类型化封装。
///
/// 字段名字符串字面量仅集中在 [tryParse] 方法内；
/// 所有调用方通过类型化属性访问字段，禁止在引擎逻辑中写 `map['fieldName']`。
///
/// 修改契约字段时，必须使用 `/extend pa-contract` 同步更新本类、
/// prompt 模板和 output_contracts.json（见 02-dart-coding §5.4）。
class AssistantTurnOutput {
  const AssistantTurnOutput({
    required this.contractVersion,
    required this.decision,
    required this.messageKind,
    required this.userMarkdown,
    this.result = const <String, dynamic>{},
    this.evidence = const <Map<String, dynamic>>[],
    this.reasoningBasis = const <Map<String, dynamic>>[],
    this.selfCheck = const <String, dynamic>{},
    this.diagnostics = const <String, dynamic>{},
    this.modelSelfScore = const <String, dynamic>{},
    this.toolCalls = const <Map>[],
    this.slotState = const <String, dynamic>{},
    this.askUser = const <String, dynamic>{},
    this.subagentPlan = const <SubagentPlan>[],
    this.intentGraph,
    this.skillRuns = const <SkillRun>[],
    this.aggregationState,
    this.userEvents = const <UserEvent>[],
    this.uiProcessTimelineV2 = const <UiProcessTimelineEntry>[],
    this.toolPlan = const <Map<String, dynamic>>[],
    this.missingContextSlots = const <String>[],
    this.fillGuidance = const <Map<String, dynamic>>[],
    this.followupPrompt = '',
    this.processSummary = '',
    this.processReferenceCount = 0,
    this.phaseId = '',
    this.actionCode = '',
    this.reasonCode = '',
    this.reasonShort = '',
    this.narrativeSource = '',
    this.narrativeReferences = const <ProcessSourceReference>[],
    this.sessionPreferenceFacts = const <PreferenceFact>[],
    this.longTermPreferenceFacts = const <PreferenceFact>[],
  });

  final String contractVersion;

  /// `{ "nextAction": "...", "confidence": 0.0-1.0, "reasoning": "..." }`
  final Map<String, dynamic> decision;

  /// `"progress" | "answer" | "ask_user" | "error" | "fallback"`
  final String messageKind;

  /// 面向用户的完整 Markdown 回答（质量红线见 prompt 模板）。
  final String userMarkdown;

  /// `{ "text": "...", "summary": "...", "actionHints": [...], "interpretation": "..." }`
  final Map<String, dynamic> result;

  /// 证据列表，每项含 `text`/`url` 等字段。
  final List<Map<String, dynamic>> evidence;

  /// 推理路径摘要列表。
  final List<Map<String, dynamic>> reasoningBasis;

  /// 自检结果，含 `checks: [ { rule, passed, evidence } ]`。
  final Map<String, dynamic> selfCheck;

  /// 诊断信息，含 `emergedTags` 等。
  final Map<String, dynamic> diagnostics;

  /// 模型自评分，含 `score`（0-100）和 `reason`。
  final Map<String, dynamic> modelSelfScore;

  /// 工具调用列表，每项含 `toolName`/`name`、`arguments`、`toolCallId`。
  final List<Map> toolCalls;

  /// 槽位状态。
  final Map<String, dynamic> slotState;

  /// 追问信息。
  final Map<String, dynamic> askUser;

  /// 子任务计划列表，每项含 `goal`、`domainId`、`problemClass`、`timeoutMs` 等。
  final List<SubagentPlan> subagentPlan;

  /// 首轮导引结构化结果。
  final IntentGraph? intentGraph;

  /// 正式编排的 skillRun 列表。
  final List<SkillRun> skillRuns;

  /// 全局聚合状态。
  final AggregationState? aggregationState;

  /// 用户可见的流式事件。
  final List<UserEvent> userEvents;

  /// 消息级过程树持久化结构。
  final List<UiProcessTimelineEntry> uiProcessTimelineV2;

  /// 工具执行计划，每项含 `tool`、`arguments`。
  final List<Map<String, dynamic>> toolPlan;

  /// 缺失的上下文槽位名称列表。
  final List<String> missingContextSlots;

  /// 补全引导列表，每项含 `guidance`。
  final List<Map<String, dynamic>> fillGuidance;

  /// 追问提示文本。
  final String followupPrompt;

  /// 过程区的一行摘要。
  final String processSummary;

  /// 过程区的可展开来源计数。
  final int processReferenceCount;

  /// 过程叙事所属阶段。
  final String phaseId;

  /// 当前叙事动作编码。
  final String actionCode;

  /// 当前叙事原因编码。
  final String reasonCode;

  /// 当前叙事短理由，优先用于流式用户态过程展示。
  final String reasonShort;

  /// 叙事来源，如 `model` / `trace_translator`。
  final String narrativeSource;

  /// 与当前叙事直接关联的引用。
  final List<ProcessSourceReference> narrativeReferences;

  /// 本会话即时生效的偏好事实。
  final List<PreferenceFact> sessionPreferenceFacts;

  /// 长期偏好事实快照。
  final List<PreferenceFact> longTermPreferenceFacts;

  // ── 快捷访问 ──────────────────────────────────────────────────────────────

  /// decision.nextAction 快捷访问。
  String get nextAction => (decision['nextAction'] as String?)?.trim() ?? '';

  /// decision.confidence 快捷访问（0.0-1.0）。
  double get confidence => (decision['confidence'] as num?)?.toDouble() ?? 0.0;

  /// modelSelfScore.score 快捷访问（0-100）。
  double get selfScoreValue =>
      (modelSelfScore['score'] as num?)?.toDouble() ?? 0.0;

  /// diagnostics.emergedTags 快捷访问。
  List<Map<String, dynamic>> get emergedTags =>
      (diagnostics['emergedTags'] as List?)
          ?.whereType<Map>()
          .map((m) => m.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];

  // ── 解析 ──────────────────────────────────────────────────────────────────

  /// 从 LLM 输出 JSON 解析为类型化对象。返回 null 表示不是已知契约格式。
  ///
  /// **唯一允许使用字段名字符串字面量的地方。**
  /// 调用方通过类型化属性访问结果，禁止在此方法外写 `map['fieldName']`。
  static AssistantTurnOutput? tryParse(Map<String, dynamic> json) {
    final version = (json['contractVersion'] as String?)?.trim() ?? '';
    final Map<String, dynamic> payload;

    if (version == kAssistantTurnCurrentVersion ||
        version == kAssistantTurnLegacyVersion) {
      payload = json;
    } else {
      // 兼容旧包裹格式 { "assistant_turn_v2": { ... } }
      final wrapped = json[kAssistantTurnV2WrapKey];
      if (wrapped is Map) {
        payload = wrapped.cast<String, dynamic>();
      } else {
        return null;
      }
    }

    return AssistantTurnOutput(
      contractVersion: kAssistantTurnCurrentVersion,
      decision:
          (payload['decision'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      messageKind: (payload['messageKind'] as String?)?.trim() ?? '',
      userMarkdown: (payload['userMarkdown'] as String?)?.trim() ?? '',
      result:
          (payload['result'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      evidence: _parseMapList(payload['evidence']),
      reasoningBasis: _parseMapList(payload['reasoningBasis']),
      selfCheck:
          (payload['selfCheck'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      diagnostics:
          (payload['diagnostics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      modelSelfScore:
          (payload['modelSelfScore'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      toolCalls:
          (payload['toolCalls'] as List?)?.whereType<Map>().toList() ??
          const <Map>[],
      slotState:
          (payload['slotState'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      askUser:
          (payload['askUser'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      subagentPlan: _parseMapList(
        payload['subagentPlan'],
      ).map(SubagentPlan.fromJson).toList(growable: false),
      intentGraph: (payload['intentGraph'] as Map?) != null
          ? IntentGraph.fromJson(
              (payload['intentGraph'] as Map).cast<String, dynamic>(),
            )
          : null,
      skillRuns: _parseMapList(
        payload['skillRuns'],
      ).map(SkillRun.fromJson).toList(growable: false),
      aggregationState: (payload['aggregationState'] as Map?) != null
          ? AggregationState.fromJson(
              (payload['aggregationState'] as Map).cast<String, dynamic>(),
            )
          : null,
      userEvents: _parseMapList(
        payload['userEvents'],
      ).map(UserEvent.fromJson).toList(growable: false),
      uiProcessTimelineV2: _parseMapList(
        payload['uiProcessTimelineV2'],
      ).map(UiProcessTimelineEntry.fromJson).toList(growable: false),
      toolPlan: _parseMapList(payload['toolPlan']),
      missingContextSlots:
          (payload['missingContextSlots'] as List?)?.whereType<String>().toList(
            growable: false,
          ) ??
          const <String>[],
      fillGuidance: _parseMapList(payload['fillGuidance']),
      followupPrompt: (payload['followupPrompt'] as String?) ?? '',
      processSummary:
          (payload['processSummary'] as String?)?.trim() ??
          (payload['processSummaryV1'] as String?)?.trim() ??
          '',
      processReferenceCount:
          (payload['processReferenceCount'] as num?)?.toInt() ??
          (payload['processReferenceCountV1'] as num?)?.toInt() ??
          0,
      phaseId: (payload['phaseId'] as String?)?.trim() ?? '',
      actionCode: (payload['actionCode'] as String?)?.trim() ?? '',
      reasonCode: (payload['reasonCode'] as String?)?.trim() ?? '',
      reasonShort:
          (payload['reasonShort'] as String?)?.trim() ??
          (payload['thinkingText'] as String?)?.trim() ??
          '',
      narrativeSource:
          (payload['source'] as String?)?.trim() ??
          (payload['narrativeSource'] as String?)?.trim() ??
          '',
      narrativeReferences: _parseMapList(
        payload['references'] ?? payload['narrativeReferences'],
      ).map(ProcessSourceReference.fromJson).toList(growable: false),
      sessionPreferenceFacts: _parseMapList(
        payload['sessionPreferenceFacts'],
      ).map(PreferenceFact.fromJson).toList(growable: false),
      longTermPreferenceFacts: _parseMapList(
        payload['longTermPreferenceFacts'],
      ).map(PreferenceFact.fromJson).toList(growable: false),
    );
  }

  /// 序列化为契约信封 Map，contractVersion 始终为 [kAssistantTurnCurrentVersion]。
  Map<String, dynamic> toEnvelopeMap() => <String, dynamic>{
    'contractVersion': kAssistantTurnCurrentVersion,
    'decision': decision,
    'messageKind': messageKind,
    'userMarkdown': userMarkdown,
    'result': result,
    'evidence': evidence,
    'reasoningBasis': reasoningBasis,
    'selfCheck': selfCheck,
    'diagnostics': diagnostics,
    'modelSelfScore': modelSelfScore,
    'toolCalls': toolCalls,
    'slotState': slotState,
    'askUser': askUser,
    'subagentPlan': subagentPlan
        .map((item) => item.toJson())
        .toList(growable: false),
    'intentGraph': intentGraph?.toJson(),
    'skillRuns': skillRuns.map((item) => item.toJson()).toList(growable: false),
    'aggregationState': aggregationState?.toJson(),
    'userEvents': userEvents
        .map((item) => item.toJson())
        .toList(growable: false),
    'uiProcessTimelineV2': uiProcessTimelineV2
        .map((item) => item.toJson())
        .toList(growable: false),
    'toolPlan': toolPlan,
    'missingContextSlots': missingContextSlots,
    'fillGuidance': fillGuidance,
    'followupPrompt': followupPrompt,
    'processSummary': processSummary,
    'processReferenceCount': processReferenceCount,
    'phaseId': phaseId,
    'actionCode': actionCode,
    'reasonCode': reasonCode,
    'reasonShort': reasonShort,
    'source': narrativeSource,
    'references': narrativeReferences
        .map((item) => item.toJson())
        .toList(growable: false),
    'sessionPreferenceFacts': sessionPreferenceFacts
        .map((item) => item.toJson())
        .toList(growable: false),
    'longTermPreferenceFacts': longTermPreferenceFacts
        .map((item) => item.toJson())
        .toList(growable: false),
  };

  static List<Map<String, dynamic>> _parseMapList(dynamic value) {
    if (value is List) {
      return value
          .whereType<Map>()
          .map((m) => m.cast<String, dynamic>())
          .toList(growable: false);
    }
    return const <Map<String, dynamic>>[];
  }

  /// 是否为已知的支持版本。
  static bool isSupportedVersion(String version) =>
      version == kAssistantTurnCurrentVersion ||
      version == kAssistantTurnLegacyVersion;
}

// ─────────────────────────────────────────────────────────────────────────────

class AssistantTurnDecision {
  const AssistantTurnDecision({
    required this.nextAction,
    required this.messageKind,
  });

  final AssistantNextAction nextAction;
  final AssistantMessageKind messageKind;

  bool get isAnswerReady =>
      nextAction == AssistantNextAction.answer &&
      messageKind != AssistantMessageKind.progress;

  /// 从已构建的 answerPayload Map 中解析决策。
  /// answerPayload 是 _parseAnswerPayload 的返回值（非原始 LLM JSON），
  /// 其 key 由引擎内部确定，属于受控 Map。
  static AssistantTurnDecision fromAnswerPayload(
    Map<String, dynamic> answerPayload,
  ) {
    final decisionMap =
        (answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextActionRaw = (decisionMap['nextAction'] as String?)?.trim() ?? '';
    final messageKindRaw =
        (answerPayload['messageKind'] as String?)?.trim() ?? '';
    return AssistantTurnDecision(
      nextAction: parseNextAction(nextActionRaw),
      messageKind: parseMessageKind(messageKindRaw),
    );
  }

  /// 兼容旧调用方式（保留向后兼容，新代码请使用 [fromAnswerPayload]）。
  static AssistantTurnDecision fromMaps({
    required Map<String, dynamic> structured,
    Map<String, dynamic> answerPayload = const <String, dynamic>{},
  }) {
    final decisionFromStructured =
        (structured['decisionJson'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final decisionFromPayload =
        (answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextActionRaw =
        (decisionFromStructured['nextAction'] as String?)?.trim().isNotEmpty ==
            true
        ? (decisionFromStructured['nextAction'] as String).trim()
        : (decisionFromPayload['nextAction'] as String?)?.trim() ?? '';
    final messageKindRaw =
        (structured['messageKind'] as String?)?.trim().isNotEmpty == true
        ? (structured['messageKind'] as String).trim()
        : (answerPayload['messageKind'] as String?)?.trim() ?? '';
    return AssistantTurnDecision(
      nextAction: parseNextAction(nextActionRaw),
      messageKind: parseMessageKind(messageKindRaw),
    );
  }
}

AssistantNextAction parseNextAction(String value) {
  switch (value.trim()) {
    case 'tool_call':
      return AssistantNextAction.toolCall;
    case 'answer':
      return AssistantNextAction.answer;
    case 'ask_user':
      return AssistantNextAction.askUser;
    case 'retry':
      return AssistantNextAction.retry;
    case 'abort':
      return AssistantNextAction.abort;
    default:
      return AssistantNextAction.unknown;
  }
}

AssistantMessageKind parseMessageKind(String value) {
  switch (value.trim()) {
    case 'progress':
      return AssistantMessageKind.progress;
    case 'answer':
      return AssistantMessageKind.answer;
    case 'ask_user':
      return AssistantMessageKind.askUser;
    case 'error':
      return AssistantMessageKind.error;
    case 'fallback':
      return AssistantMessageKind.fallback;
    default:
      return AssistantMessageKind.unknown;
  }
}
