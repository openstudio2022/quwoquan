import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';

/// Centralized copy bank for baseline default-processing output.
///
/// This narrows user-visible fallback prose to a single file so governance
/// tests can block new copy from spreading back into runtime orchestrators.
enum ToolAssessMessageKey {
  budgetExhausted,
  loopDetected,
  toolFailedStop,
  toolFailedRetry,
  batchUsable,
  fastConverged,
  slowConverged,
  needMoreSearchMulti,
  needMoreSearchSingle,
  replanFast,
  replanMulti,
  replanSingle,
  finalMulti,
  finalRefs,
  finalDefault,
}

class DefaultProcessingCopyBank {
  const DefaultProcessingCopyBank._();

  static const String runtimeFallbackDisabledReason =
      'runtime_fallback_disabled';
  static const String runtimeFallbackDisabledInterpretation =
      'runtime_fallback_disabled';

  static String heuristicReasoning({
    required ProblemClass problemClass,
    required AnswerShape answerShape,
    required bool hasReferences,
  }) {
    if (problemClass == ProblemClass.taskExecution) {
      return hasReferences
          ? '完成这件事需要的信息已经齐了一部分，我先把能直接推进的步骤收拢出来。'
          : '先把完成这个动作需要的关键信息补齐，避免中途反复补问。';
    }
    if (answerShape == AnswerShape.comparison) {
      return hasReferences
          ? '关键差异已经有依据了，我先按维度收拢成更容易比较的结论。'
          : '先把真正影响选择的维度立住，再继续补最缺的那一块。';
    }
    if (answerShape == AnswerShape.options) {
      return hasReferences
          ? '候选方案已经回来一批，我先筛掉不够相关的，再看哪些值得保留。'
          : '先把候选范围和适用边界拆开，避免后面方案越列越散。';
    }
    if (problemClass == ProblemClass.realtimeInfo) {
      return hasReferences
          ? '当前状态已经有依据了，我先把真正会影响判断的变化收拢起来。'
          : '先补当前状态这一块，避免把过期信息直接当成结论。';
    }
    if (problemClass == ProblemClass.complexReasoning ||
        problemClass == ProblemClass.evidenceLookup) {
      return hasReferences
          ? '关键依据已经有一批了，我先对齐一致和分歧，再决定结论站到哪里。'
          : '先把判断框架搭起来，后面沿着最缺的证据继续补。';
    }
    return hasReferences ? '已经把能相互印证的信息收拢出来了。' : '先给一个不会误导你的下一步。';
  }

  static String fallbackReason({
    required ProblemClass problemClass,
    required bool hasMissingCriticalSlots,
    required bool hasEvidence,
    required bool evidenceSafe,
    required bool hasToolError,
  }) {
    if (hasMissingCriticalSlots) {
      return '我先不硬答，想先把会直接影响结论的关键信息补齐。';
    }
    if (!evidenceSafe && hasEvidence) {
      return '目前已经有一部分可参考信息，但还没稳到可以直接当成最终结论。';
    }
    if (!evidenceSafe && hasToolError) {
      return '这轮外部来源不够稳定，所以先只保留已经站稳的部分。';
    }
    if (problemClass == ProblemClass.complexReasoning ||
        problemClass == ProblemClass.evidenceLookup) {
      return '这类问题更怕方向混在一起，所以需要先把判断框架摆清楚。';
    }
    return '我先给你一个最低可用、不会误导你的版本。';
  }

  static String askUserPrompt(String slotId) {
    switch (slotId) {
      case 'location':
      case 'city':
      case 'destination':
        return '先告诉我更具体的地点或对象范围，我再继续收敛。';
      case 'budget':
        return '再告诉我你的大概预算，我就能把推荐范围压得更准。';
      case 'time':
      case 'timeScope':
      case 'date':
      case 'dateRange':
      case 'days':
        return '再告诉我时间范围或关键时点，我就能继续往下收敛。';
      case 'audience':
      case 'companionType':
        return '如果你愿意，再说一下更偏向谁用或适用于什么场景，我会把建议调得更贴合。';
      case 'constraints':
        return '如果你有必须满足或明确排除的条件，也可以补一句，我会直接按这个收窄范围。';
      default:
        return '我还差一个会影响结论的关键信息，你补一句我就继续。';
    }
  }

  static List<String> planningFramework({
    required ProblemClass problemClass,
    required AnswerShape answerShape,
  }) {
    if (problemClass == ProblemClass.taskExecution) {
      return const <String>[
        '先确认动作目标和限制，避免执行一半再返工。',
        '再核对完成动作所需的关键信息和前置条件。',
        '最后只保留可以立即执行的下一步。',
      ];
    }
    if (answerShape == AnswerShape.comparison) {
      return const <String>[
        '先立住比较维度，避免不同标准混在一起。',
        '再核对每个候选项最关键的证据和限制。',
        '最后只保留真正影响选择的差异点。',
      ];
    }
    if (answerShape == AnswerShape.options) {
      return const <String>[
        '先圈定候选范围，避免方案越查越散。',
        '再看适用场景和风险边界。',
        '最后筛掉不值得保留的选项。',
      ];
    }
    if (problemClass == ProblemClass.complexReasoning ||
        problemClass == ProblemClass.evidenceLookup) {
      return const <String>[
        '先确认问题里的核心对象和限制，避免检索跑偏。',
        '再核对最关键的外部依据和相互冲突的点。',
        '最后只保留当前最稳、最能支撑结论的部分。',
      ];
    }
    return const <String>[
      '先确认问题里最影响结论的条件。',
      '再核对最关键的外部依据。',
      '最后只保留当前最稳的结论。',
    ];
  }

  static String fallbackHeading(String key) {
    switch (key) {
      case 'clarify':
        return '## 还差一个关键信息';
      case 'bounded':
        return '## 已确认的关键信息';
      case 'retry':
        return '## 还需要再补一轮核对';
      case 'realtime':
        return '## 当前信息还不够稳';
      default:
        return '## 先给你一个稳妥版本';
    }
  }

  static const String checkedFocusHeading = '### 我重点核对了';
  static const String referencesHeading = '### 参考来源';
  static const String currentReferencesHeading = '### 当前可参考来源';
  static const String nextStepHeading = '### 下一步我会沿这几块继续收敛';
  static const String carryOverHeading = '### 当前已承接的信息';

  static const String clarifyInterpretation = '需要补齐关键信息后再继续';
  static const String boundedInterpretation = '证据未完全收敛，先输出部分结论';
  static const String retryInterpretation = '证据不足，先输出可执行框架';
  static const String realtimeInterpretation = '实时证据不足';
  static const String defaultInterpretation = '默认兜底回答';

  static const String boundedPlainText = '先把已经确认的关键信息整理给你。';
  static const String retryPlainText = '这类问题还需要再补一轮核对。';
  static const String realtimePlainText = '当前信息还不够稳，我先不硬答。';
  static const String defaultPlainText = '我先给你一个稳妥版本。';
  static const String boundedClaim = '已确认的关键信息';

  static String defaultSummary({
    required ProblemClass problemClass,
    required AnswerShape answerShape,
  }) {
    if (problemClass == ProblemClass.taskExecution) {
      return '已经拿到一部分可执行线索，可以先收拢成下一步。';
    }
    if (answerShape == AnswerShape.comparison) {
      return '已经有一批能支撑比较的资料，可以先整理出关键差异。';
    }
    if (answerShape == AnswerShape.options) {
      return '已经拿到一批候选线索，可以先筛出更值得保留的几个方向。';
    }
    if (problemClass == ProblemClass.realtimeInfo) {
      return '已经拿到一部分最新信息，可以先整理出会影响当前判断的部分。';
    }
    return '已经拿到的资料足够先整理出和你问题最相关的结论。';
  }

  static String answerHeading({
    required ProblemClass problemClass,
    required AnswerShape answerShape,
    required String target,
  }) {
    if (problemClass == ProblemClass.taskExecution) {
      return '## 可执行下一步';
    }
    if (answerShape == AnswerShape.comparison) {
      return '## 当前比较结论';
    }
    if (answerShape == AnswerShape.options) {
      return '## 当前候选方案';
    }
    if (target.isNotEmpty && target.length <= 24) {
      return '## 关于 $target 的当前结论';
    }
    return '## 当前结论';
  }

  static String interpretation({
    required ProblemClass problemClass,
    required AnswerShape answerShape,
  }) {
    if (problemClass == ProblemClass.taskExecution) {
      return '基于已拿到信息整理出的执行建议';
    }
    if (problemClass == ProblemClass.realtimeInfo) {
      return '基于已拿到资料整理出的当前判断';
    }
    if (answerShape == AnswerShape.comparison) {
      return '基于已拿到资料整理出的比较结论';
    }
    if (answerShape == AnswerShape.options) {
      return '基于已拿到资料整理出的候选方案';
    }
    return '基于已拿到资料整理出的当前最稳结论';
  }

  static const String boundedSafetyLine = '这一版只保留已经能相互印证的内容，剩下还不稳的部分我不会硬补。';
  static const String realtimeSafetyLine = '这类问题对时效很敏感，所以我先不把不稳的数据当成最终结论。';
  static const String realtimeScopeLine = '如果你愿意，可以补充更具体的时间、地点或对象，我会继续收窄范围。';
  static const String realtimeOutputLine = '现在这一版只保留方向性的判断，不把未经确认的细节写死。';
  static const String defaultSafetyLine = '我暂时不把还没核稳的内容直接当答案。';
  static const String defaultContinueLine = '如果你愿意，我可以继续按更具体的条件帮你收敛。';

  static String toolAssessMessage(
    ToolAssessMessageKey key, {
    int queryCount = 0,
  }) {
    switch (key) {
      case ToolAssessMessageKey.budgetExhausted:
        return '已经有一批能支撑判断的信息了，我先把最重要的结论整理给你。';
      case ToolAssessMessageKey.loopDetected:
        return '这几次拿到的新信息不多，我不想让你白等，先基于已确认的内容回答。';
      case ToolAssessMessageKey.toolFailedStop:
        return '这轮搜索不太稳定，我先把已经确认的部分整理给你。';
      case ToolAssessMessageKey.toolFailedRetry:
        return '这一批资料不够稳，我换个来源再试一下。';
      case ToolAssessMessageKey.batchUsable:
        return '这批方向已经有可用信息了，我先帮你收拢重复和差异。';
      case ToolAssessMessageKey.fastConverged:
        return '关键信息已经够用了，我开始直接整理回答。';
      case ToolAssessMessageKey.slowConverged:
        return '我先不继续拖时间了，基于已经确认的信息整理给你。';
      case ToolAssessMessageKey.needMoreSearchMulti:
        return '现在主线已经有了，但还差一处会影响判断的空缺，我再替你补查那一块。';
      case ToolAssessMessageKey.needMoreSearchSingle:
        return '这轮结果还差一点落点，我换更具体的问法再查一次。';
      case ToolAssessMessageKey.replanFast:
        return '关键信息已经够了，我直接整理给你。';
      case ToolAssessMessageKey.replanMulti:
        return '目前大方向已经有了，但还缺一处会影响结论的信息，我再补一轮。';
      case ToolAssessMessageKey.replanSingle:
        return '还差一块关键信息能让结论更稳，我继续补一下。';
      case ToolAssessMessageKey.finalMulti:
        return '关键信息已经够用了，我开始把$queryCount个方向里的重复和差异收拢成结论。';
      case ToolAssessMessageKey.finalRefs:
        return '关键依据已经基本对齐了，我开始按你更容易看的顺序整理答案。';
      case ToolAssessMessageKey.finalDefault:
        return '关键信息已经够用了，我开始整理答案。';
    }
  }

  static String conversationKernelAskPrompt(String slotId) {
    switch (slotId) {
      case 'location':
      case 'city':
        return '告诉我更具体的地点，比如“深圳”或一个更明确的区域。';
      case 'destination':
        return '告诉我你关注的目的地或范围，我再继续帮你收敛。';
      case 'budget':
        return '再告诉我预算范围，我就能把建议压得更准。';
      case 'time':
      case 'timeScope':
      case 'date':
      case 'dateRange':
      case 'days':
        return '再告诉我时间范围或关键时点，我就能继续往下收窄。';
      case 'audience':
      case 'companionType':
        return '再补一句更偏向谁用或适用于什么场景，我会把建议调得更贴合。';
      case 'constraints':
        return '如果你有必须满足或明确排除的条件，也可以补一句。';
      default:
        return '再补一句最关键的条件，我就继续帮你收敛。';
    }
  }
}
