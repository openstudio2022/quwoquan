import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantDisplayStateProjection', () {
    test('renderAnswerBlocksToMarkdown 会修复历史 displayState 中的坏表格和小数', () {
      final markdown =
          renderAnswerBlocksToMarkdown(const <AssistantAnswerDisplayBlock>[
            AssistantAnswerDisplayBlock(
              blockId: 'answer_markdown',
              kind: DisplayBlockKind.markdown,
              body:
                  '| 维度 | 华为云 | 阿里云 | 腾讯云 |\n'
                  '| :\n'
                  '- -- | :\n'
                  '- -- | :\n'
                  '- -- | :\n'
                  '- -- |\n'
                  '| 核心优势 | 算力强 | 生态成熟 | 社交生态强 |\n'
                  '\n'
                  '- 上证指数：\n'
                  '\n'
                  '3288. 41点，下跌0.20%',
            ),
          ]);

      expect(markdown, contains('| :--- | :--- | :--- | :--- |'));
      expect(markdown, contains('上证指数：3288.41点，下跌0.20%'));
    });

    test('renderAnswerBlocksToMarkdown 不展示 assistant_turn 协议 JSON', () {
      const internalEnvelope =
          '{"contractId":"assistant_turn","decision":{"nextAction":"abort"},'
          '"messageKind":"fallback","userMarkdown":"",'
          '"result":{"interpretation":"answer_organization_failed"}}';

      final markdown =
          renderAnswerBlocksToMarkdown(const <AssistantAnswerDisplayBlock>[
            AssistantAnswerDisplayBlock(
              blockId: 'answer_markdown',
              kind: DisplayBlockKind.markdown,
              body: internalEnvelope,
            ),
          ]);
      final state = buildAssistantDisplayState(
        answerMarkdown: internalEnvelope,
      );

      expect(markdown, isEmpty);
      expect(state.answer.blocks, isEmpty);
    });

    test('检索引用展示优先使用 timeline 中的完整 references 列表', () {
      const allReferences = <RetrievalProcessingReference>[
        RetrievalProcessingReference(
          title: '来源 A',
          url: 'https://docs.example.com/a',
          source: 'docs.example.com',
        ),
        RetrievalProcessingReference(
          title: '来源 B',
          url: 'https://docs.example.com/b',
          source: 'docs.example.com',
        ),
        RetrievalProcessingReference(
          title: '来源 C',
          url: 'https://docs.example.com/c',
          source: 'docs.example.com',
        ),
      ];
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'r',
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
            references: allReferences,
          ),
        ],
        retrievalProcessing: const RetrievalProcessingSnapshot(
          searchedDocumentCount: 24,
          processedDocumentCount: 8,
          acceptedDocumentCount: 2,
          processingSummary: '已完成检索筛选。',
          acceptedReferences: <RetrievalProcessingReference>[
            RetrievalProcessingReference(
              title: '来源 A',
              url: 'https://docs.example.com/a',
              source: 'docs.example.com',
            ),
          ],
        ),
      );

      final statsBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'retrieval_reference_stats',
      );
      expect(statsBlock.title, '搜索了 24 篇，接纳了 2 篇');
      expect(statsBlock.references, hasLength(3));
      expect(statsBlock.references.last.url, 'https://docs.example.com/c');
    });

    test('会从 snapshots 和 timeline 生成结构化过程区与答案区', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
          ProcessTimelineFrame(
            frameId: 'rd',
            stepId: ProcessStepId.retrievalDesign,
            status: JourneyStageStatus.completed,
            headline: '我会先按关键信号拆开检索。',
            detail: '检索词会围绕“昨天A股 大涨 原因”、“昨日 A股 涨停 板块”展开',
          ),
          ProcessTimelineFrame(
            frameId: 'r',
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
          ),
          ProcessTimelineFrame(
            frameId: 'a',
            stepId: ProcessStepId.answerOrganization,
            status: JourneyStageStatus.active,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '我先确认你的核心问题和约束。',
          retrievalDesignNarrative: '我会先按关键信号拆开检索。',
          concernPoints: <String>['先看事实', '再看建议'],
          resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
            RunArtifactsUnderstandingResolutionItem(
              kind: 'geo_default',
              title: '已采用默认城市',
              detail: '你没有指定城市，我先按深圳理解并检索。',
              resolvedValue: '深圳',
              defaultApplied: true,
              visibleInUnderstanding: true,
            ),
          ],
        ),
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processedDocumentCount: 4,
          acceptedDocumentCount: 2,
          processingSummary: '我筛出了能直接支撑结论的结果。',
          selectedKeyPoints: <String>['结果更新时间一致', '关键数值可交叉验证'],
          acceptedReferences: <RetrievalProcessingReference>[
            RetrievalProcessingReference(
              title: '来源 A',
              url: 'https://example.com/a',
              source: 'Example',
            ),
          ],
        ),
        answerProcessing: const RunArtifactsAnswerProcessing(
          readinessSummary: '我开始把已确认的信息整理成回答。',
          keyFacts: <String>['先说结论', '再补充建议'],
        ),
        answerMarkdown: '先给结论，再给建议。',
        finalAnswerReady: true,
      );

      expect(state.process.activeStepId, ProcessStepId.answerOrganization);
      expect(state.process.blocks.first.title, contains('我先确认你的核心问题和约束'));
      final understandingBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'understanding_narrative',
      );
      expect(understandingBlock.body, isEmpty);
      final queryDesignBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'retrieval_query_design',
      );
      expect(queryDesignBlock.title, contains('我会先按关键信号拆开检索'));
      expect(
        queryDesignBlock.body,
        contains('检索词会围绕“昨天A股 大涨 原因”、“昨日 A股 涨停 板块”展开'),
      );
      final statsBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'retrieval_reference_stats',
      );
      expect(statsBlock.title, '搜索了 4 篇，接纳了 2 篇');
      final retrievalNarrativeBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'retrieval_narrative',
      );
      expect(retrievalNarrativeBlock.title, contains('能直接支撑结论'));
      expect(retrievalNarrativeBlock.body, isEmpty);
      expect(
        state.process.blocks.any(
          (block) => block.blockId == 'understanding_resolution_items',
        ),
        isFalse,
        reason: '不应再有独立的 resolution items 列表块，信息已融入 summary',
      );
      expect(
        state.process.blocks.any(
          (block) =>
              block.kind == ProcessDisplayBlockKind.references &&
              block.references.isNotEmpty,
        ),
        isTrue,
      );
      expect(state.answer.blocks, hasLength(1));
      expect(state.answer.blocks.first.kind, DisplayBlockKind.markdown);
      expect(
        renderAnswerBlocksToMarkdown(state.answer.blocks),
        contains('先给结论，再给建议。'),
      );
      expect(
        renderAnswerBlocksToPlainText(state.answer.blocks),
        contains('先给结论，再给建议。'),
      );
    });

    test('显式 answer blocks 会优先保留，不再从自由文本猜结构', () {
      final state = buildAssistantDisplayState(
        explicitState: const AssistantDisplayState(
          answer: AssistantAnswerDisplayState(
            summary: '结果已整理完成',
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'summary',
                kind: DisplayBlockKind.paragraph,
                title: '结论',
                body: '今天适合轻装出门。',
              ),
              AssistantAnswerDisplayBlock(
                blockId: 'actions',
                kind: DisplayBlockKind.bulletList,
                items: <AssistantDisplayItem>[
                  AssistantDisplayItem(itemId: '1', body: '带一把折叠伞'),
                  AssistantDisplayItem(itemId: '2', body: '晚点出门更稳妥'),
                ],
              ),
            ],
          ),
        ),
        answerMarkdown: '这段自由文本不应该再决定答案结构。',
      );

      expect(state.answer.blocks, hasLength(2));
      expect(renderAnswerBlocksToMarkdown(state.answer.blocks), contains('结论'));
      expect(
        renderAnswerBlocksToMarkdown(state.answer.blocks),
        contains('- 带一把折叠伞'),
      );
      expect(
        renderAnswerBlocksToPlainText(state.answer.blocks),
        contains('晚点出门更稳妥'),
      );
    });

    test('显式 answer blocks 缺少 summary 时，会回填 answerProcessing 的 bounded 提示', () {
      final state = buildAssistantDisplayState(
        explicitState: const AssistantDisplayState(
          answer: AssistantAnswerDisplayState(
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'bounded_answer',
                kind: DisplayBlockKind.paragraph,
                body: '先给你一版受限答案。',
              ),
            ],
          ),
        ),
        answerProcessing: const RunArtifactsAnswerProcessing(
          readinessSummary: '当前证据还不够稳定，这版先作为 bounded answer 展示。',
        ),
      );

      expect(
        state.answer.summary,
        equals('当前证据还不够稳定，这版先作为 bounded answer 展示。'),
      );
      expect(
        renderAnswerBlocksToMarkdown(state.answer.blocks),
        contains('受限答案'),
      );
    });

    test('显式 answer blocks 保持优先，不再从 markdown 反向补结构', () {
      final state = buildAssistantDisplayState(
        explicitState: const AssistantDisplayState(
          answer: AssistantAnswerDisplayState(
            summary: '天气结论已整理',
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'summary',
                kind: DisplayBlockKind.paragraph,
                body: '深圳明天有雨，建议带伞。',
              ),
            ],
          ),
        ),
        answerMarkdown: '2026-04-10 深圳有雨，建议带伞。',
      );

      expect(state.answer.blocks.length, 1);
      expect(
        renderAnswerBlocksToPlainText(state.answer.blocks),
        contains('深圳明天有雨'),
      );
      expect(
        renderAnswerBlocksToPlainText(state.answer.blocks),
        isNot(contains('2026-04-10')),
      );
    });

    test('显式 process blocks 只有局部时，不因 orphan understanding 再生成检索词设计块', () {
      final state = buildAssistantDisplayState(
        explicitState: const AssistantDisplayState(
          process: AssistantProcessDisplayState(
            blocks: <AssistantProcessDisplayBlock>[
              AssistantProcessDisplayBlock(
                blockId: 'retrieval_narrative',
                stepId: ProcessStepId.retrievalProcessing,
                status: JourneyStageStatus.completed,
                kind: ProcessDisplayBlockKind.summary,
                title: '我先锁定对应交易日，再核对市场主线。',
              ),
            ],
          ),
        ),
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
          ProcessTimelineFrame(
            frameId: 'r',
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          intentSummary: '若误入快照的噪声检索词：2026-04-07 A股 大涨 原因',
        ),
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processingSummary: '已经把可用结果筛过一轮。',
        ),
      );

      expect(
        state.process.blocks.any(
          (block) =>
              block.blockId == 'retrieval_narrative' &&
              block.title.contains('对应交易日'),
        ),
        isTrue,
      );
      expect(
        state.process.blocks.any(
          (block) => block.blockId == 'retrieval_query_design',
        ),
        isFalse,
      );
      final narrative = state.process.blocks
          .where((block) => block.blockId == 'understanding_narrative')
          .map((block) => '${block.title}\n${block.body}')
          .join('\n');
      expect(
        narrative,
        isNot(contains('2026-04-07 A股 大涨 原因')),
        reason: 'intentSummary 不参与过程叙事，避免噪声检索词污染',
      );
    });

    test('retrieval design 与已有总结重复时不会在叙事中重复堆叠 headline', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
          ProcessTimelineFrame(
            frameId: 'rd',
            stepId: ProcessStepId.retrievalDesign,
            status: JourneyStageStatus.completed,
            headline: '我会先锁定对应交易日，再核对市场主线。',
          ),
          ProcessTimelineFrame(
            frameId: 'r',
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '我会先锁定对应交易日，再核对市场主线。',
        ),
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processingSummary: '我会先锁定对应交易日，再核对市场主线。',
        ),
      );

      final narrative = state.process.blocks.firstWhere(
        (block) => block.blockId == 'understanding_narrative',
      );
      expect(
        narrative.body,
        isNot(contains('我会先锁定对应交易日，再核对市场主线')),
        reason: '与主 summary 重复的 retrieval design headline 应被去重',
      );
    });

    test('summary 很短但有 resolution items 时，主叙事保持模型原文', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '获取深圳今日天气',
          resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '外出建议带伞',
              visibleInUnderstanding: true,
            ),
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '体感偏热',
              visibleInUnderstanding: true,
            ),
          ],
        ),
      );

      final summaryBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'understanding_narrative',
      );
      expect(
        summaryBlock.title,
        contains('获取深圳今日天气'),
        reason: '原始 summary 应保留',
      );
      expect(
        summaryBlock.title,
        isNot(contains('外出建议带伞')),
        reason: 'resolution items 不再参与 runtime 主叙事拼接',
      );
      expect(
        state.process.blocks.any(
          (block) => block.blockId == 'understanding_resolution_items',
        ),
        isFalse,
        reason: '不应有独立列表块',
      );
    });

    test('summary 已包含 resolution 信息时，不再由 runtime 追加内容', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '你想了解天气并查看出门建议。',
          resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '外出建议带伞',
              visibleInUnderstanding: true,
            ),
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '出行建议优先地铁',
              visibleInUnderstanding: true,
            ),
          ],
        ),
      );

      final summaryBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'understanding_narrative',
      );
      expect(
        summaryBlock.title,
        equals('你想了解天气并查看出门建议。'),
        reason: '主叙事只保留模型字段，不再拼接 resolution items',
      );
    });

    test('summary 已含一部分信息时，不再追加缺失补充内容', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '获取天气及穿衣、出行建议',
          resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '查询范围为深圳',
              visibleInUnderstanding: true,
            ),
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '外出前查看降雨变化',
              visibleInUnderstanding: true,
            ),
          ],
        ),
      );

      final summaryBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'understanding_narrative',
      );
      expect(
        summaryBlock.title,
        equals('获取天气及穿衣、出行建议'),
        reason: '主叙事不再由 runtime 拼接补充信息',
      );
    });

    test('summary 为空时，不再从 resolution items 反向生成主叙事', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '',
          resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '外出建议带伞',
              visibleInUnderstanding: true,
            ),
            RunArtifactsUnderstandingResolutionItem(
              kind: 'detail_note',
              title: '补充说明',
              detail: '出行建议优先地铁',
              visibleInUnderstanding: true,
            ),
          ],
        ),
      );

      expect(
        state.process.blocks.any(
          (block) => block.blockId == 'understanding_narrative',
        ),
        isFalse,
      );
    });

    test('retrieval design timeline 会生成独立 query design block', () {
      final state = buildAssistantDisplayState(
        processTimeline: const <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
          ProcessTimelineFrame(
            frameId: 'rd',
            stepId: ProcessStepId.retrievalDesign,
            status: JourneyStageStatus.completed,
            headline: '沿着交易日确认几个维度把检索线索铺开',
            detail:
                '我会先沿着交易日确认这一条线继续核对，先把相对时间落成具体日期\n检索词会围绕“2026-04-07 A股 大涨 原因”展开',
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '',
        ),
      );

      final queryDesignBlock = state.process.blocks.firstWhere(
        (block) => block.blockId == 'retrieval_query_design',
      );
      expect(queryDesignBlock.title, contains('沿着交易日确认几个维度把检索线索铺开'));
      expect(
        queryDesignBlock.body,
        contains('我会先沿着交易日确认这一条线继续核对，先把相对时间落成具体日期'),
      );
      expect(queryDesignBlock.body, contains('检索词会围绕“2026-04-07 A股 大涨 原因”展开'));
    });
  });
}
