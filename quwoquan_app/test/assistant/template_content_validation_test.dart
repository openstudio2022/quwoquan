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
        contains('运行时会直接抽取 `understandingSnapshot.userFacingSummary`'),
        reason: 'planner.global_plan 应明确声明阶段1主展示字段会被运行时直接抽取',
      );
      expect(
        planner,
        contains('优先确认哪些判断维度'),
        reason: 'planner.global_plan 应明确要求理解阶段把判断维度并入用户主叙事',
      );
      expect(
        synth,
        contains(
          '运行时会直接抽取 `retrievalProcessing.processingSummary`、`answerProcessing.readinessSummary` 与 `userMarkdown`',
        ),
        reason: 'synthesizer.final_answer 应明确声明阶段3字段会被运行时直接抽取',
      );
      expect(
        synth,
        contains('处理了多少资料、接纳了多少资料及其列表'),
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

    test('phase output contract 保留 reasonShort 并切到单字段直接抽取流式', () {
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
      expect(phasePlan, contains('最小稳定优先字段'));
      expect(phasePlan, contains('唯一推荐保留的历史评估字段'));
      expect(phasePlan, contains('不能假设运行时还会再开一个独立“历史判定”模型轮次'));
      expect(
        phasePlan,
        contains('规划阶段主展示只来自 `understandingSnapshot.userFacingSummary`'),
        reason: '规划阶段 contract 应明确声明主展示字段会被直接抽取流式展示',
      );
      expect(
        phasePlan,
        contains('后续回答阶段默认不得回写或覆盖 `understandingSnapshot`'),
        reason: '规划阶段 contract 应冻结普通两轮链路里的理解快照',
      );
      expect(
        phaseAnswer,
        contains(
          '运行时会直接抽取 `retrievalProcessing.processingSummary`、`answerProcessing.readinessSummary` 与 `userMarkdown`',
        ),
        reason: '回答阶段 contract 应明确声明主展示字段会被直接抽取流式展示',
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
      expect(phaseAnswer, contains('唯一建议保留的历史评估字段'));
      expect(phaseAnswer, contains('`userMarkdown` 必须是自然最终答案'));
      expect(phaseAnswer, contains('处理了多少资料、接纳了多少资料及其列表'));
      expect(phaseAnswer, contains('不得重写第一轮已经确认的 `understandingSnapshot`'));
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
      expect(phaseAnswer, contains('`retrievalProcessing`'));
      expect(phaseAnswer, contains('普通问题默认只保留两轮模型交互'));
      expect(phaseAnswer, contains('`userMarkdown` 只能承载最终答案'));
      expect(phaseAnswer, contains('最小稳定优先字段'));
      expect(phaseAnswer, contains('historicalThinkingSnapshot'));
      expect(phaseAnswer, isNot(contains('## 问题理解')));
      expect(phaseAnswer, isNot(contains('## 关键观点')));
      expect(phaseAnswer, isNot(contains('## 回答概要')));
      expect(synth, contains('`<conversation_spine>` 是本轮主线'));
      expect(synth, contains('普通问题默认只保留两轮模型交互'));
      expect(synth, contains('retrievalProcessing.processingSummary'));
      expect(synth, contains('答案会围绕哪些重点收束'));
      expect(synth, contains('优先依据 `problemClass + answerShape` 选择答案形态'));
      expect(synth, contains('如果用户没有明确索取联系方式'));
      expect(synth, contains('不要使用 Markdown heading 语法'));
      expect(synth, contains('最小稳定合同'));
      expect(planner, contains('needsRecheckFacts'));
      expect(planner, contains('queryDesignSummary'));
      expect(planner, contains('不存在单独的“历史判定”模型轮次'));
      expect(
        planner,
        contains('后续回答阶段默认不得重写本轮 `understandingSnapshot.userFacingSummary`'),
      );
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
