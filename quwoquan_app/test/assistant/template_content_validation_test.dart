import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:test/test.dart';

/// 对 manifest.json 中每个模板文件运行真实 TemplateValidator 校验。
/// 此测试确保：
///   1. 每个模板文件能从磁盘正常读取
///   2. 每个模板通过 TemplateValidator.validate() 校验（不会被 TemplateRegistry 静默跳过）
///   3. 任何模板更新后都必须保证校验通过，否则 TemplateRegistry 不会加载该模板
void main() {
  const validator = TemplateValidator();
  const manifestPath = 'assets/assistant/prompts/manifest.json';

  late List<_TemplateEntry> templateEntries;

  setUpAll(() {
    final manifest = File(manifestPath);
    expect(manifest.existsSync(), isTrue, reason: 'manifest.json 必须存在');
    final decoded = jsonDecode(manifest.readAsStringSync()) as Map;
    final templates =
        (decoded['templates'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    expect(templates, isNotEmpty, reason: 'manifest 至少包含 1 个模板');
    templateEntries = templates
        .map((item) {
          return _TemplateEntry(
            metaPath: (item['metaPath'] as String?) ?? '',
            contentPath: (item['contentPath'] as String?) ?? '',
          );
        })
        .toList(growable: false);
  });

  group('manifest 所有模板通过 TemplateValidator 校验', () {
    test('每个模板文件可读取且通过校验', () {
      final failures = <String>[];
      for (final entry in templateEntries) {
        if (entry.metaPath.isEmpty || entry.contentPath.isEmpty) {
          failures.add('条目缺少 metaPath 或 contentPath: $entry');
          continue;
        }
        final contentFile = File(entry.contentPath);
        if (!contentFile.existsSync()) {
          failures.add('文件不存在: ${entry.contentPath}');
          continue;
        }
        final metaFile = File(entry.metaPath);
        if (!metaFile.existsSync()) {
          failures.add('meta 文件不存在: ${entry.metaPath}');
          continue;
        }
        final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
        final templateId = (meta['templateId'] as String?)?.trim() ?? '';
        if (templateId.isEmpty) {
          failures.add('templateId 为空: ${entry.metaPath}');
          continue;
        }
        final content = contentFile.readAsStringSync();
        final result = validator.validate(
          templateId: templateId,
          content: content,
        );
        if (!result.isValid) {
          failures.add(
            '$templateId (${entry.contentPath}) 校验失败:\n'
            '  ${result.errors.join('\n  ')}',
          );
        }
      }
      expect(
        failures,
        isEmpty,
        reason:
            '以下模板校验失败，将被 TemplateRegistry 静默跳过导致运行时错误:\n'
            '${failures.join('\n')}',
      );
    });

    test('每个模板 templateId 唯一', () {
      final ids = <String>[];
      final duplicates = <String>[];
      for (final entry in templateEntries) {
        if (entry.metaPath.isEmpty) continue;
        final metaFile = File(entry.metaPath);
        if (!metaFile.existsSync()) continue;
        final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
        final id = (meta['templateId'] as String?)?.trim() ?? '';
        if (id.isEmpty) continue;
        if (ids.contains(id)) {
          duplicates.add(id);
        } else {
          ids.add(id);
        }
      }
      expect(
        duplicates,
        isEmpty,
        reason: '以下 templateId 重复注册，会导致版本覆盖: $duplicates',
      );
    });

    test('planner.global_plan 无重复数据块', () {
      const plannerContentPath =
          'assets/assistant/prompts/global/planner.global_plan.md';
      final content = File(plannerContentPath).readAsStringSync();
      final startCount = RegExp(
        r'=== CONTEXT_DATA_START ===',
      ).allMatches(content).length;
      final endCount = RegExp(
        r'=== CONTEXT_DATA_END ===',
      ).allMatches(content).length;
      expect(
        startCount,
        1,
        reason:
            'planner.global_plan.md 有 $startCount 个 CONTEXT_DATA_START，应为 1（无重复内容）',
      );
      expect(
        endCount,
        1,
        reason:
            'planner.global_plan.md 有 $endCount 个 CONTEXT_DATA_END，应为 1（无重复内容）',
      );
    });

    test('主 prompt 改为显式约束单字段流式抽取并收紧历史噪音', () {
      const plannerContentPath =
          'assets/assistant/prompts/global/planner.global_plan.md';
      const synthContentPath =
          'assets/assistant/prompts/global/synthesizer.final_answer.md';
      final planner = File(plannerContentPath).readAsStringSync();
      final synth = File(synthContentPath).readAsStringSync();

      expect(
        planner,
        contains('`understandingSnapshot.userFacingSummary` 是阶段 1 唯一主展示字段'),
        reason: 'planner.global_plan 应明确声明阶段1主展示字段',
      );
      expect(
        planner,
        contains('不要在本阶段输出 `decision.nextAction=answer`'),
        reason: 'planner.global_plan 应明确禁止规划阶段直接成答',
      );
      expect(
        planner,
        contains('禁止使用 bullet point'),
        reason: 'planner.global_plan 应禁止结构化标签拼接',
      );
      expect(
        planner,
        contains('calendarContext'),
        reason: 'planner.global_plan 应明确要求周几类时间锚点参考日历上下文',
      );
      expect(
        planner,
        contains('禁止保留 `最近`、`最新`、`近期`、`未来`'),
        reason: 'planner.global_plan 应明确禁止 query literal 残留模糊时间词',
      );
      expect(
        synth,
        contains('`retrievalProcessing.processingSummary` 是本轮唯一流式展示的过程字段'),
        reason: 'synthesizer.final_answer 应明确声明 processingSummary 是唯一流式展示的过程字段',
      );
      expect(
        synth,
        contains('calendarContext'),
        reason: 'synthesizer.final_answer 应明确要求回答阶段沿用同一份时间锚点',
      );
      expect(
        synth,
        contains(
          '`processedDocumentCount`、`acceptedDocumentCount`、`acceptedReferences`',
        ),
        reason: 'synthesizer.final_answer 应明确保留检索资料计数与引用列表，但不混入主叙事',
      );
      expect(
        planner,
        isNot(contains('understanding.streamText')),
        reason: 'planner.global_plan 不应再把嵌套 understanding.streamText 当作流式真相源',
      );
      expect(
        synth,
        isNot(contains('answerProcessing.streamText')),
        reason:
            'synthesizer.final_answer 不应再把嵌套 answerProcessing.streamText 当作流式真相源',
      );
      expect(
        planner,
        isNot(contains('uiProcessTimelineV2')),
        reason: '主 planner prompt 不应继续携带历史 process timeline 字段名',
      );
      expect(
        synth,
        isNot(contains('whyThisAnswer')),
        reason: '主 synthesizer prompt 不应继续携带旧 diagnostics 字段',
      );
    });

    test('phase output contract 收口为纯结构约束', () {
      const phasePlanPath =
          'assets/assistant/prompts/global/phase.output_contract.plan.md';
      const phaseAnswerPath =
          'assets/assistant/prompts/global/phase.output_contract.answer.md';
      final phasePlan = File(phasePlanPath).readAsStringSync();
      final phaseAnswer = File(phaseAnswerPath).readAsStringSync();

      expect(
        phasePlan,
        contains('reasonShort'),
        reason: '规划阶段 contract 仍需兼容当前 reasonShort 流式读取',
      );
      expect(
        phasePlan,
        contains('`toolArgs.query` 或 `toolArgs.queries[]` 必须是最终可执行检索词'),
      );
      expect(phasePlan, contains('`understandingSnapshot.userFacingSummary`'));
      expect(phasePlan, isNot(contains('  - `answer`')));
      expect(
        phaseAnswer,
        contains('`retrievalProcessing.processingSummary`'),
        reason: '回答阶段 contract 应保留最小过程字段约束',
      );
      expect(
        phasePlan,
        isNot(contains('understanding.streamText')),
        reason: '规划阶段 contract 不应再依赖 understanding.streamText',
      );
      expect(
        phaseAnswer,
        isNot(contains('answerProcessing.streamText')),
        reason: '回答阶段 contract 不应再依赖 answerProcessing.streamText',
      );
      expect(
        phaseAnswer,
        contains('userMarkdown'),
        reason: '回答阶段 contract 仍需约束最终成答字段 userMarkdown',
      );
      expect(
        phaseAnswer,
        contains('toolCalls'),
        reason: '回答阶段 contract 应支持 canonical toolCalls 补查协议',
      );
      expect(
        phaseAnswer,
        isNot(contains('answerGateAssessment')),
        reason: '回答阶段 contract 不应再携带旧 gate 字段',
      );
      expect(phaseAnswer, isNot(contains('如果决定继续补查')));
    });

    test('回答阶段 prompt 改为自然成答并注册 evidence_digest 模板', () {
      const manifestPath = 'assets/assistant/prompts/manifest.json';
      const evidenceDigestMetaPath =
          'assets/assistant/prompts/global/evidence_digest.meta.json';
      const evidenceDigestContentPath =
          'assets/assistant/prompts/global/evidence_digest.md';
      const phaseAnswerPath =
          'assets/assistant/prompts/global/phase.output_contract.answer.md';
      const plannerContentPath =
          'assets/assistant/prompts/global/planner.global_plan.md';
      const synthContentPath =
          'assets/assistant/prompts/global/synthesizer.final_answer.md';
      final manifest = File(manifestPath).readAsStringSync();
      final evidenceDigestMeta = File(
        evidenceDigestMetaPath,
      ).readAsStringSync();
      final evidenceDigest = File(evidenceDigestContentPath).readAsStringSync();
      final phaseAnswer = File(phaseAnswerPath).readAsStringSync();
      final planner = File(plannerContentPath).readAsStringSync();
      final synth = File(synthContentPath).readAsStringSync();

      expect(
        manifest,
        isNot(contains('planner.continuity_resolution.meta.json')),
      );
      expect(manifest, isNot(contains('planner.continuity_resolution.md')));
      expect(phaseAnswer, contains('`retrievalProcessing.processingSummary`'));
      expect(phaseAnswer, contains('`toolCalls`'));
      expect(phaseAnswer, isNot(contains('answerGateAssessment')));
      expect(phaseAnswer, contains('`userMarkdown`'));
      expect(phaseAnswer, contains('`decision.nextAction=answer`'));
      expect(phaseAnswer, isNot(contains('## 问题理解')));
      expect(phaseAnswer, isNot(contains('## 关键观点')));
      expect(phaseAnswer, isNot(contains('## 回答概要')));
      expect(synth, contains('普通问题默认只保留两次模型阶段'));
      expect(synth, contains('retrievalProcessing.processingSummary'));
      expect(synth, contains('tool_call'));
      expect(synth, isNot(contains('answerGateAssessment')));
      expect(
        synth,
        contains(
          '`processedDocumentCount`、`acceptedDocumentCount`、`acceptedReferences`',
        ),
      );
      expect(planner, contains('search_iteration_state'));
      expect(
        planner,
        contains(
          '`taskGraph.tasks[*].toolArgs.query` 或 `taskGraph.tasks[*].toolArgs.queries[]` 必须是可直接发送给搜索 provider 的最终自然语言检索词',
        ),
      );
      expect(planner, contains('“无需检索即可直接回答”属于 runtime-owned shortcut'));
      expect(planner, contains('最近 / 最新 / 近期'));
      expect(synth, isNot(contains('## 问题理解')));
      expect(synth, isNot(contains('## 关键观点')));
      expect(synth, isNot(contains('## 回答概要')));
      expect(manifest, contains('evidence_digest.meta.json'));
      expect(manifest, contains('evidence_digest.md'));
      expect(evidenceDigestMeta, contains('"templateId": "evidence_digest"'));
      expect(evidenceDigest, contains('处理问题阶段'));
      expect(evidenceDigest, contains('processingSummary'));
      expect(evidenceDigest, contains('selectedKeyPoints'));
      expect(evidenceDigest, contains('acceptedReferences'));
      expect(evidenceDigest, contains('不能退化成“处理了 x 篇 / 接纳了 x 篇”这类纯统计播报'));
      expect(synth, contains('`userMarkdown` 不能写成“我会先给结论，再说驱动因素”这类答案结构说明'));
    });
  });
}

class _TemplateEntry {
  const _TemplateEntry({required this.metaPath, required this.contentPath});
  final String metaPath;
  final String contentPath;

  @override
  String toString() => 'meta=$metaPath content=$contentPath';
}
