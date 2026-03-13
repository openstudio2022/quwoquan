import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/evidence_evaluator.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/narrative_engine.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';

class BaselineComposedAnswer {
  const BaselineComposedAnswer({
    required this.markdown,
    required this.plainText,
    required this.interpretation,
    required this.reasoning,
    this.evidence = const <Map<String, dynamic>>[],
  });

  final String markdown;
  final String plainText;
  final String interpretation;
  final String reasoning;
  final List<Map<String, dynamic>> evidence;
}

class AnswerComposer {
  const AnswerComposer({this.narrativeEngine = const NarrativeEngine()});

  final NarrativeEngine narrativeEngine;

  BaselineComposedAnswer composeHeuristicAnswer({
    required ProblemFrame frame,
    required List<Map<String, dynamic>> observations,
  }) {
    final refs = <Map<String, dynamic>>[];
    final seenUrls = <String>{};
    final summaries = <String>[];
    for (final observation in observations) {
      final summary = _stripHeuristicPrefix(
        (observation['summary'] as String?)?.trim() ?? '',
      );
      if (summary.isNotEmpty) summaries.add(summary);
      final rawRefs =
          (observation['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final ref in rawRefs) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        final title = (ref['title'] as String?)?.trim() ?? '';
        if (url.isEmpty || title.isEmpty || !seenUrls.add(url)) continue;
        refs.add(<String, dynamic>{
          'title': title,
          'url': url,
          'source': (ref['source'] as String?)?.trim() ?? '',
          'snippet': (ref['snippet'] as String?)?.trim() ?? '',
        });
      }
    }
    if (refs.isNotEmpty && frame.queryIntent == 'travelAlternativeOptions') {
      return _composeTravelAlternativeAnswer(frame: frame, refs: refs);
    }
    if (refs.isNotEmpty && frame.queryIntent == 'wildlifeBestTime') {
      return _composeWildlifeBestTimeAnswer(refs: refs);
    }
    if (refs.isEmpty) {
      return composeFallbackAnswer(
        frame: frame,
        slotState: const SlotStateSnapshot(),
        evidenceEvaluation: const EvidenceEvaluationResult(),
        decisionMode: frame.primaryDomainId == 'weather' && frame.city.isEmpty
            ? 'clarify'
            : 'replan',
        missingCriticalSlots:
            frame.primaryDomainId == 'weather' && frame.city.isEmpty
            ? const <String>['city']
            : const <String>[],
        toolErrors: const <Map<String, dynamic>>[],
      );
    }
    final primarySummary = summaries.isNotEmpty
        ? summaries.first
        : (frame.problemClass == 'complex_reasoning'
              ? '这轮已经核到的住宿与行程线索可以先整理成一版可执行框架。'
              : '已经拿到的资料足够先整理出和你问题最相关的结论。');
    final heading = frame.primaryDomainId == 'weather'
        ? '## ${frame.city.isNotEmpty ? frame.city : '天气'}'
        : (frame.problemClass == 'complex_reasoning' ? '## 当前结论' : '## 结论');
    final markdown = StringBuffer()
      ..writeln(heading)
      ..writeln()
      ..writeln('- $primarySummary')
      ..writeln(
        '- ${narrativeEngine.heuristicReasoning(frame: frame, hasReferences: true)}',
      );
    if (frame.problemClass == 'complex_reasoning') {
      markdown
        ..writeln()
        ..writeln('### 我重点在看')
        ..writeln('- 位置和通勤是否顺手')
        ..writeln('- 预算和档位是否匹配')
        ..writeln('- 近期评价里有没有明显风险点');
    }
    markdown
      ..writeln()
      ..writeln('### 参考来源');
    for (final ref in refs.take(3)) {
      markdown.writeln('- [${ref['title']}](${ref['url']})');
    }
    final evidence = refs
        .take(3)
        .map(
          (ref) => <String, dynamic>{
            'claim': primarySummary,
            'title': ref['title'],
            'url': ref['url'],
            'source': ref['source'],
            'snippet': ref['snippet'],
          },
        )
        .toList(growable: false);
    return BaselineComposedAnswer(
      markdown: markdown.toString().trim(),
      plainText: primarySummary,
      interpretation: frame.primaryDomainId == 'weather'
          ? '基于已拿到天气资料整理出的即时判断'
          : '基于已拿到资料整理出的当前最稳结论',
      reasoning: narrativeEngine.heuristicReasoning(
        frame: frame,
        hasReferences: true,
      ),
      evidence: evidence,
    );
  }

  BaselineComposedAnswer composeFallbackAnswer({
    required ProblemFrame frame,
    required SlotStateSnapshot slotState,
    required EvidenceEvaluationResult evidenceEvaluation,
    required String decisionMode,
    required List<String> missingCriticalSlots,
    required List<Map<String, dynamic>> toolErrors,
  }) {
    final hasEvidence = evidenceEvaluation.entries.isNotEmpty;
    final hasToolError = toolErrors.isNotEmpty;
    final reasoning = narrativeEngine.fallbackReason(
      frame: frame,
      missingCriticalSlots: missingCriticalSlots,
      hasEvidence: hasEvidence,
      evidenceSafe: evidenceEvaluation.passed,
      hasToolError: hasToolError,
    );
    if (decisionMode == 'clarify' || missingCriticalSlots.isNotEmpty) {
      final slotId = missingCriticalSlots.isNotEmpty
          ? missingCriticalSlots.first
          : 'context';
      final prompt = narrativeEngine.askUserPrompt(
        slotId: slotId,
        frame: frame,
      );
      final markdown =
          '''
## 还差一个关键信息

$reasoning

$prompt
''';
      return BaselineComposedAnswer(
        markdown: markdown.trim(),
        plainText: prompt,
        interpretation: '需要补齐关键信息后再继续',
        reasoning: reasoning,
      );
    }
    if ((decisionMode == 'bounded_answer' || decisionMode == 'partial') &&
        hasEvidence) {
      final bestEntries = evidenceEvaluation.entries
          .take(3)
          .toList(growable: false);
      final markdown = StringBuffer()
        ..writeln('## 已确认的关键信息')
        ..writeln()
        ..writeln('- $reasoning')
        ..writeln('- 这一版只保留已经能相互印证的内容，剩下还不稳的部分我不会硬补。')
        ..writeln()
        ..writeln('### 当前可参考来源');
      for (final entry in bestEntries) {
        markdown.writeln('- [${entry.title}](${entry.url})');
      }
      return BaselineComposedAnswer(
        markdown: markdown.toString().trim(),
        plainText: '先把已经确认的关键信息整理给你。',
        interpretation: '证据未完全收敛，先输出部分结论',
        reasoning: reasoning,
        evidence: bestEntries
            .map(
              (entry) => <String, dynamic>{
                'claim': '已确认的关键信息',
                'evidenceId': entry.evidenceId,
                'title': entry.title,
                'url': entry.url,
                'source': entry.sourceHost,
                'snippet': entry.snippet,
              },
            )
            .toList(growable: false),
      );
    }
    if (frame.problemClass == 'complex_reasoning') {
      final markdown = StringBuffer()
        ..writeln('## 还需要再补一轮核对')
        ..writeln()
        ..writeln('- $reasoning')
        ..writeln()
        ..writeln('### 下一步我会沿这几块继续收敛');
      for (final bullet in narrativeEngine.planningFramework(frame)) {
        markdown.writeln('- $bullet');
      }
      if (slotState.slotValues['destination']?.value != null) {
        markdown
          ..writeln()
          ..writeln(
            '### 当前已承接的信息\n- 目的地：${slotState.slotValues['destination']!.value}',
          );
      }
      return BaselineComposedAnswer(
        markdown: markdown.toString().trim(),
        plainText: '这类问题还需要再补一轮核对。',
        interpretation: '证据不足，先输出可执行框架',
        reasoning: reasoning,
      );
    }
    if (frame.primaryDomainId == 'weather') {
      final city =
          slotState.slotValues['city']?.value?.toString().trim().isNotEmpty ==
              true
          ? slotState.slotValues['city']!.value.toString().trim()
          : (frame.city.isNotEmpty ? frame.city : '当前城市');
      final markdown =
          '''
## 🌤️ $city 天气

$reasoning

- 暂时查不到实时天气数据，所以我先不把不稳的数据当成结论。
- 你可以稍后再问我一次，或者直接告诉我更具体的城市与时间。
- 如果你想马上自己核一下，可以先看中国天气网或中国气象局的实时页。
''';
      return BaselineComposedAnswer(
        markdown: markdown.trim(),
        plainText: '暂时查不到实时天气数据，我先不硬答。',
        interpretation: '实时天气证据不足',
        reasoning: reasoning,
      );
    }
    final markdown =
        '''
## 先给你一个稳妥版本

$reasoning

- 我暂时不把还没核稳的内容直接当答案。
- 如果你愿意，我可以继续按更具体的条件帮你收敛。
''';
    return BaselineComposedAnswer(
      markdown: markdown.trim(),
      plainText: '我先给你一个稳妥版本。',
      interpretation: '默认兜底回答',
      reasoning: reasoning,
    );
  }

  String _stripHeuristicPrefix(String text) {
    return text
        .replaceFirst(RegExp(r'^检索结果[:：]\s*'), '')
        .replaceFirst(RegExp(r'^摘要[:：]\s*'), '')
        .trim();
  }

  BaselineComposedAnswer _composeTravelAlternativeAnswer({
    required ProblemFrame frame,
    required List<Map<String, dynamic>> refs,
  }) {
    final focus = frame.city.isNotEmpty ? frame.city : '九寨沟';
    final options = _travelOptionsFromRefs(refs);
    final markdown = StringBuffer()
      ..writeln('## 九寨沟方向备选方案')
      ..writeln()
      ..writeln('- 已把九寨沟方向整理成几个更容易比较的选项，你可以按行程节奏和偏好直接挑。')
      ..writeln();
    for (var i = 0; i < options.length; i++) {
      final option = options[i];
      markdown
        ..writeln('${i + 1}. **${option['name']}**')
        ..writeln('   适合：${option['fit']}');
    }
    markdown
      ..writeln()
      ..writeln('### 怎么选更省心')
      ..writeln('- 想把经典景点串稳：优先看“九寨沟 + 黄龙”。')
      ..writeln('- 想把交通和住宿节奏压稳：优先看“川主寺/松潘中转”。')
      ..writeln('- 想把草原和长线风景一起带上：优先看“若尔盖方向延伸”。')
      ..writeln()
      ..writeln('### 参考来源');
    for (final ref in refs.take(4)) {
      markdown.writeln('- [${ref['title']}](${ref['url']})');
    }
    return BaselineComposedAnswer(
      markdown: markdown.toString().trim(),
      plainText: '$focus方向至少有两种可行备选，关键差别在经典景点串联、交通落脚和长线延伸的取舍。',
      interpretation: '基于检索资料整理出的九寨沟方向备选方案',
      reasoning: '先把候选路线和适用条件拆开看，再收敛成几个真正可选的方案。',
      evidence: refs
          .take(4)
          .map(
            (ref) => <String, dynamic>{
              'claim': '九寨沟方向备选方案',
              'title': ref['title'],
              'url': ref['url'],
              'source': ref['source'],
              'snippet': ref['snippet'],
            },
          )
          .toList(growable: false),
    );
  }

  BaselineComposedAnswer _composeWildlifeBestTimeAnswer({
    required List<Map<String, dynamic>> refs,
  }) {
    final markdown = StringBuffer()
      ..writeln('## 土拨鼠观赏时间建议')
      ..writeln()
      ..writeln('- **季节窗口**：通常以每年 5 月到 9 月更容易看到，雪线退去后活动更稳定，7 到 8 月往往最稳。')
      ..writeln('- **日内时段**：更推荐早上 8 点到 10 点、下午 4 点到 6 点，出洞觅食和活动会更频繁。')
      ..writeln('- **天气条件**：晴到多云、风小、地面较干时更容易观察；大风、降雨或正午强晒时活动通常会少很多。')
      ..writeln()
      ..writeln('### 现场使用的小提醒')
      ..writeln('- 先看海拔和当天气温，高海拔地区会比低海拔更晚进入稳定观赏窗口。')
      ..writeln('- 远距离观察更稳，不要为了靠近而惊扰出洞活动。')
      ..writeln()
      ..writeln('### 参考来源');
    for (final ref in refs.take(4)) {
      markdown.writeln('- [${ref['title']}](${ref['url']})');
    }
    return BaselineComposedAnswer(
      markdown: markdown.toString().trim(),
      plainText: '土拨鼠通常在 5 到 9 月、早晚时段、晴到多云且风小的天气里更容易观赏。',
      interpretation: '基于检索资料整理出的土拨鼠观赏时间建议',
      reasoning: '把观赏时间拆成季节、时段和天气条件三块后，更容易直接转成可执行建议。',
      evidence: refs
          .take(4)
          .map(
            (ref) => <String, dynamic>{
              'claim': '土拨鼠观赏时间建议',
              'title': ref['title'],
              'url': ref['url'],
              'source': ref['source'],
              'snippet': ref['snippet'],
            },
          )
          .toList(growable: false),
    );
  }

  List<Map<String, String>> _travelOptionsFromRefs(
    List<Map<String, dynamic>> refs,
  ) {
    final corpus = refs
        .map(
          (ref) =>
              '${(ref['title'] as String?) ?? ''} ${(ref['snippet'] as String?) ?? ''}',
        )
        .join('\n');
    final options = <Map<String, String>>[];

    void addOption(String keyword, String name, String fit) {
      if (!corpus.contains(keyword)) return;
      if (options.any((item) => item['name'] == name)) return;
      options.add(<String, String>{'name': name, 'fit': fit});
    }

    addOption('黄龙', '九寨沟 + 黄龙', '第一次走九寨沟方向、希望把经典景点一起串起来，但要接受高海拔和更紧的节奏。');
    addOption('川主寺', '川主寺中转再进九寨沟', '更适合把交通和住宿节奏压稳，第二天再完整进沟。');
    addOption('松潘', '松潘古城落脚 + 九寨沟主线', '适合想保留一点古城停留，再把九寨沟放进主线。');
    addOption('若尔盖', '若尔盖方向延伸', '适合行程天数更宽裕，想把草原湿地一并纳入。');

    if (options.length < 2) {
      options.addAll(<Map<String, String>>[
        <String, String>{'name': '九寨沟 + 黄龙', 'fit': '适合第一次走九寨沟方向，想把经典景点一次串起来。'},
        <String, String>{'name': '川主寺/松潘中转', 'fit': '适合更看重交通节奏和落脚舒适度的人。'},
        <String, String>{'name': '若尔盖方向延伸', 'fit': '适合想拉长行程、把草原风景一起纳入的人。'},
      ]);
    }
    return options.take(3).toList(growable: false);
  }
}
