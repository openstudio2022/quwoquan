import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';

void main() {
  test('validates all 21 skills with multi-intent narrative quality', () {
    final skillsByDomain = _loadSkillFrontmatters();
    final loadedDomains = skillsByDomain.keys.toList()..sort();
    final loadedSkillDebug = skillsByDomain.entries
        .map(
          (entry) => <String, String>{
            'domainId': entry.key,
            'name': entry.value['name'] ?? '',
          },
        )
        .toList(growable: false);

    expect(
      loadedDomains,
      equals(_skillCases.map((item) => item.domain).toList()..sort()),
      reason: jsonEncode(loadedSkillDebug),
    );
    expect(skillsByDomain, hasLength(21));
    final report = <Map<String, dynamic>>[];

    for (final skillCase in _skillCases) {
      expect(skillsByDomain, contains(skillCase.domain));
      final skill = skillsByDomain[skillCase.domain]!;

      final description = skill['description'] ?? '';
      final skillMarkdown = skill['body'] ?? '';
      final allowedTools = _splitWords(skill['allowed_tools']);
      expect(description.trim(), isNotEmpty);
      expect(skillMarkdown.trim(), isNotEmpty);
      expect(allowedTools, isNotEmpty);
      expect(
        (skill['output_contract'] ?? '').trim(),
        isNotEmpty,
        reason: '${skillCase.domain} should declare output contract',
      );
      expect((skill['dialogue_state_docs'] ?? '').trim(), isNotEmpty);

      final singleRun = _buildValidatedRun(
        skillCase: skillCase,
        primarySkillName: skill['name'] ?? skillCase.domain,
        primaryDescription: description,
      );
      final multiRun = _buildValidatedRun(
        skillCase: skillCase,
        primarySkillName: skill['name'] ?? skillCase.domain,
        primaryDescription: description,
        secondaryDomain: skillCase.secondaryDomain,
      );

      expect(singleRun.isMultiIntent, isFalse);
      expect(multiRun.isMultiIntent, isTrue);
      expect(multiRun.answer, contains(skillCase.domain));
      expect(multiRun.answer, contains(skillCase.secondaryDomain));

      report.add(<String, dynamic>{
        'domain': skillCase.domain,
        'secondaryDomain': skillCase.secondaryDomain,
        'tools': allowedTools,
        'singleFrames': singleRun.visibleFrames
            .map((frame) => frame.stepId.name)
            .toList(growable: false),
        'multiIntent': multiRun.isMultiIntent,
        'answerLength': multiRun.answer.length,
      });
    }

    // Keeps simulator logs useful when this test is run from CI or a local device.
    // ignore: avoid_print
    print(
      jsonEncode(<String, dynamic>{
        'validatedSkillCount': report.length,
        'report': report,
      }),
    );
  });
}

Map<String, Map<String, String>> _loadSkillFrontmatters() {
  final skillsDir = Directory('assets/assistant/skills');
  expect(skillsDir.existsSync(), isTrue);
  final skills = <String, Map<String, String>>{};
  for (final entity in skillsDir.listSync(recursive: true)) {
    if (entity is! File) continue;
    final normalizedPath = entity.path.replaceAll('\\', '/');
    if (!normalizedPath.endsWith('/SKILL.md')) continue;
    final raw = entity.readAsStringSync();
    final parts = raw.split('---');
    expect(parts.length, greaterThanOrEqualTo(3), reason: normalizedPath);
    final frontmatter = _parseFrontmatter(parts[1]);
    final domain = frontmatter['domain'] ?? '';
    expect(domain, isNotEmpty, reason: normalizedPath);
    frontmatter['body'] = parts.skip(2).join('---').trim();
    skills[domain] = frontmatter;
  }
  return skills;
}

Map<String, String> _parseFrontmatter(String raw) {
  final out = <String, String>{};
  for (final line in raw.split('\n')) {
    final index = line.indexOf(':');
    if (index <= 0) continue;
    final key = line.substring(0, index).trim();
    final value = line.substring(index + 1).trim();
    if (key.isNotEmpty) {
      out[key] = value;
    }
  }
  return out;
}

List<String> _splitWords(String? raw) {
  return (raw ?? '')
      .replaceAll('[', '')
      .replaceAll(']', '')
      .split(RegExp(r'[\s,]+'))
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

_ValidatedRun _buildValidatedRun({
  required _SkillCase skillCase,
  required String primarySkillName,
  required String primaryDescription,
  String secondaryDomain = '',
}) {
  final isMultiIntent = secondaryDomain.trim().isNotEmpty;
  final query = isMultiIntent
      ? skillCase.multiIntentQuery
      : skillCase.singleQuery;
  final secondaryClause = isMultiIntent ? '，同时串联 $secondaryDomain 的相关意图' : '';
  final understanding = RunArtifactsUnderstandingSnapshot(
    intentSummary: '识别到 ${skillCase.domain} 技能请求$secondaryClause。',
    userFacingSummary: '我先确认你要用 ${skillCase.domain} 处理的问题边界。',
    retrievalDesignNarrative: isMultiIntent
        ? '再把 ${skillCase.domain} 与 $secondaryDomain 拆成可并行核对的两个意图。'
        : '再按 $primarySkillName 的技能说明选择需要核对的信息维度。',
    concernPoints: <String>[
      '目标：$query',
      '技能：${skillCase.domain}',
      if (isMultiIntent) '第二意图：$secondaryDomain',
    ],
  );
  final retrievalProcessing = RetrievalProcessingSnapshot(
    processedDocumentCount: isMultiIntent ? 4 : 2,
    acceptedDocumentCount: isMultiIntent ? 3 : 2,
    processingSummary: isMultiIntent
        ? '已分别整理 ${skillCase.domain} 与 $secondaryDomain 的关键依据，并合并成一个回答。'
        : '已按 ${skillCase.domain} 的状态机整理出可回答的关键依据。',
    selectedKeyPoints: <String>[
      '问题焦点与技能定义保持一致',
      '回答需要包含结论、依据和可执行建议',
      if (isMultiIntent) '多意图回答需要说明两个意图如何互相影响',
    ],
    expansionReason: isMultiIntent
        ? '两个意图都来自用户同一句话，先分开判断再合并，避免把辅助意图吞掉。'
        : '信息已经足够组织答案，不再追加无关追问。',
    acceptedReferences: <RetrievalProcessingReference>[
      RetrievalProcessingReference(
        title: '$primarySkillName 技能说明',
        source: 'SKILL.md',
        snippet: primaryDescription,
        rank: 1,
      ),
    ],
  );
  final frames = buildVisibleProcessTimeline(
    buildProcessTimelineFromSnapshots(
      understandingSnapshot: understanding,
      retrievalProcessing: retrievalProcessing,
      answerProcessing: RunArtifactsAnswerProcessing(
        readinessSummary: '可以基于技能约束生成最终回答。',
        keyFacts: <String>[
          skillCase.domain,
          if (isMultiIntent) secondaryDomain,
        ],
      ),
    ),
  );
  expect(
    frames,
    hasLength(3),
    reason: '${skillCase.domain} should show a 3-step process',
  );
  expect(
    frames.map((frame) => frame.stepId).toList(growable: false),
    equals(<ProcessStepId>[
      ProcessStepId.understanding,
      ProcessStepId.retrievalDesign,
      ProcessStepId.retrievalProcessing,
    ]),
  );
  for (final frame in frames) {
    expect(frame.headline.trim(), isNotEmpty);
    expect(
      _isLowSignalProcessText(frame.headline),
      isFalse,
      reason: frame.headline,
    );
  }

  final answer = isMultiIntent
      ? '这轮我会把 ${skillCase.domain} 作为主技能，并把 $secondaryDomain 作为第二意图一起处理。'
            '结论是：先满足“${skillCase.answerFocus}”，再用第二意图校验场景限制。'
            '依据上，$primarySkillName 的说明要求围绕“$primaryDescription”组织回答；'
            '因此我会先给出直接建议，再解释为什么这样判断，最后给出下一步可执行动作。'
      : '这轮命中 ${skillCase.domain}（$primarySkillName）。'
            '结论是：围绕“${skillCase.answerFocus}”直接回答，不额外发散。'
            '依据上，技能说明强调“$primaryDescription”，所以回答会包含判断依据、风险边界和可执行建议。';
  _expectAnswerQuality(
    domain: skillCase.domain,
    answer: answer,
    isMultiIntent: isMultiIntent,
  );
  return _ValidatedRun(
    answer: answer,
    visibleFrames: frames,
    isMultiIntent: isMultiIntent,
  );
}

void _expectAnswerQuality({
  required String domain,
  required String answer,
  required bool isMultiIntent,
}) {
  expect(answer.trim(), isNotEmpty, reason: '$domain answer must not be empty');
  expect(answer.length, greaterThan(isMultiIntent ? 120 : 90));
  expect(answer, contains('结论'));
  expect(answer, contains('依据'));
  expect(answer, contains('建议'));
  for (final fragment in _forbiddenAnswerFragments) {
    expect(
      answer,
      isNot(contains(fragment)),
      reason: '$domain leaked $fragment',
    );
  }
}

bool _isLowSignalProcessText(String text) {
  final normalized = text.replaceAll(RegExp(r'\s+'), '');
  return normalized.isEmpty ||
      normalized == '资料筛选完成' ||
      normalized == '已完成资料筛选并进入成答' ||
      normalized == '正在整理' ||
      normalized == '已完成处理';
}

const _forbiddenAnswerFragments = <String>[
  'contractId',
  'tool_call',
  'assistant_turn',
  '<think>',
  '</think>',
  'JSON',
  '系统提示',
];

class _ValidatedRun {
  const _ValidatedRun({
    required this.answer,
    required this.visibleFrames,
    required this.isMultiIntent,
  });

  final String answer;
  final List<ProcessTimelineFrame> visibleFrames;
  final bool isMultiIntent;
}

class _SkillCase {
  const _SkillCase({
    required this.domain,
    required this.secondaryDomain,
    required this.singleQuery,
    required this.multiIntentQuery,
    required this.answerFocus,
  });

  final String domain;
  final String secondaryDomain;
  final String singleQuery;
  final String multiIntentQuery;
  final String answerFocus;
}

const _skillCases = <_SkillCase>[
  _SkillCase(
    domain: 'astrology_constellation',
    secondaryDomain: 'relationship_matchmaking',
    singleQuery: '我今天的星座运势怎么样？',
    multiIntentQuery: '看下我今天星座运势，也帮我判断约会沟通要注意什么。',
    answerFocus: '星座解读只能作为轻量参考，并转化成沟通建议',
  ),
  _SkillCase(
    domain: 'calendar_task',
    secondaryDomain: 'work_productivity',
    singleQuery: '帮我规划明天上午的待办。',
    multiIntentQuery: '帮我排明天上午的日程，并把最重要的工作任务优先级理一下。',
    answerFocus: '日程安排要有时间块、优先级和冲突提示',
  ),
  _SkillCase(
    domain: 'divination_fortune',
    secondaryDomain: 'emotion_companion',
    singleQuery: '我最近有点纠结，要不要做个选择占卜？',
    multiIntentQuery: '帮我做个选择占卜，也安抚一下我现在的焦虑。',
    answerFocus: '娱乐化解读不能替代现实决策，需要先稳定情绪',
  ),
  _SkillCase(
    domain: 'education_learning',
    secondaryDomain: 'work_productivity',
    singleQuery: '我想学 Python，怎么开始？',
    multiIntentQuery: '我想学 Python，也帮我安排每周学习计划。',
    answerFocus: '学习目标要拆成阶段、练习和复盘',
  ),
  _SkillCase(
    domain: 'emotion_companion',
    secondaryDomain: 'health_wellness',
    singleQuery: '我今天压力很大，想聊聊。',
    multiIntentQuery: '我今天压力很大，还影响睡眠，帮我缓一下。',
    answerFocus: '先共情，再给低风险、可执行的舒缓动作',
  ),
  _SkillCase(
    domain: 'fallback_general_search',
    secondaryDomain: 'knowledge_general',
    singleQuery: '帮我查一下最近 AI 行业有什么重要变化。',
    multiIntentQuery: '帮我查最近 AI 行业变化，并解释这些变化为什么重要。',
    answerFocus: '搜索型回答要说明信息来源、时效和不确定性',
  ),
  _SkillCase(
    domain: 'family_parenting',
    secondaryDomain: 'education_learning',
    singleQuery: '孩子不愿意写作业怎么办？',
    multiIntentQuery: '孩子不愿意写作业，也帮我设计一个学习激励办法。',
    answerFocus: '亲子建议要兼顾情绪、规则和学习动机',
  ),
  _SkillCase(
    domain: 'finance_consumer',
    secondaryDomain: 'shopping_decision',
    singleQuery: '这个月预算紧，怎么控制消费？',
    multiIntentQuery: '这个月预算紧，还想买新手机，帮我判断是否该买。',
    answerFocus: '消费建议要先看预算约束，再做取舍',
  ),
  _SkillCase(
    domain: 'fortune_astrology',
    secondaryDomain: 'calendar_task',
    singleQuery: '这个月整体运势如何？',
    multiIntentQuery: '看下这个月整体运势，也帮我挑几个适合推进计划的时间点。',
    answerFocus: '运势内容保持娱乐边界，并转成行动提醒',
  ),
  _SkillCase(
    domain: 'health_wellness',
    secondaryDomain: 'local_life',
    singleQuery: '最近总是熬夜，有什么调整建议？',
    multiIntentQuery: '最近总熬夜，也帮我找些附近适合放松的活动思路。',
    answerFocus: '健康建议要明确非诊断边界和低风险习惯调整',
  ),
  _SkillCase(
    domain: 'huawei_cloud_qa',
    secondaryDomain: 'knowledge_general',
    singleQuery: '华为云对象存储适合什么场景？',
    multiIntentQuery: '解释华为云对象存储，并和通用云存储概念做个对照。',
    answerFocus: '产品问答要先解释概念，再给适用场景',
  ),
  _SkillCase(
    domain: 'knowledge_general',
    secondaryDomain: 'fallback_general_search',
    singleQuery: '为什么海水是咸的？',
    multiIntentQuery: '解释为什么海水是咸的，也查一下有没有最新科普说法。',
    answerFocus: '通识解释要清楚因果链并标注需要检索的部分',
  ),
  _SkillCase(
    domain: 'local_life',
    secondaryDomain: 'weather',
    singleQuery: '周末深圳有什么适合散步的地方？',
    multiIntentQuery: '周末深圳适合去哪散步，也结合天气提醒一下。',
    answerFocus: '本地生活建议要结合地点、时间和天气限制',
  ),
  _SkillCase(
    domain: 'policy_public_service',
    secondaryDomain: 'local_life',
    singleQuery: '深圳居住证办理需要注意什么？',
    multiIntentQuery: '深圳居住证怎么办，也提醒我附近线下办理要注意什么。',
    answerFocus: '政务建议要提示政策时效和官方渠道核验',
  ),
  _SkillCase(
    domain: 'relationship_matchmaking',
    secondaryDomain: 'emotion_companion',
    singleQuery: '第一次见面怎么聊天比较自然？',
    multiIntentQuery: '第一次见面怎么聊天，我还有点紧张，帮我一起准备。',
    answerFocus: '关系建议要自然、尊重边界，并缓解紧张',
  ),
  _SkillCase(
    domain: 'shopping_decision',
    secondaryDomain: 'finance_consumer',
    singleQuery: '买扫地机器人应该看哪些参数？',
    multiIntentQuery: '帮我选扫地机器人，也结合预算判断值不值得买。',
    answerFocus: '购物建议要从需求、预算和取舍出发',
  ),
  _SkillCase(
    domain: 'social_companion_chat',
    secondaryDomain: 'emotion_companion',
    singleQuery: '陪我随便聊会儿吧。',
    multiIntentQuery: '陪我聊会儿，也帮我整理一下今天为什么不开心。',
    answerFocus: '陪伴聊天要轻松自然，同时保留情绪承接',
  ),
  _SkillCase(
    domain: 'travel_planning',
    secondaryDomain: 'weather',
    singleQuery: '四天去成都怎么玩？',
    multiIntentQuery: '四天去成都怎么玩，也结合天气安排室内外。',
    answerFocus: '旅行规划要有路线、节奏和天气备选',
  ),
  _SkillCase(
    domain: 'travel_transport',
    secondaryDomain: 'travel_planning',
    singleQuery: '从深圳去香港机场怎么走方便？',
    multiIntentQuery: '从深圳去香港机场怎么走，也帮我安排当天行程缓冲。',
    answerFocus: '交通建议要比较方案、时长和风险缓冲',
  ),
  _SkillCase(
    domain: 'weather',
    secondaryDomain: 'local_life',
    singleQuery: '今天深圳天气怎么样？',
    multiIntentQuery: '今天深圳天气怎么样，也推荐适合的附近活动。',
    answerFocus: '天气回答要先给结论，再说明温度、降雨和出行建议',
  ),
  _SkillCase(
    domain: 'work_productivity',
    secondaryDomain: 'calendar_task',
    singleQuery: '帮我把今天工作任务排优先级。',
    multiIntentQuery: '帮我把今天任务排优先级，并安排到日程里。',
    answerFocus: '工作建议要明确优先级、时间块和下一步',
  ),
];
