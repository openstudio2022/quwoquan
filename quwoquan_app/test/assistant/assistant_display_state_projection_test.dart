import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantDisplayStateProjection', () {
    test('会从 snapshots 和 timeline 生成结构化过程区与答案区', () {
      final state = buildAssistantDisplayState(
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
          ProcessTimelineFrame(
            frameId: 'a',
            stepId: ProcessStepId.answerOrganization,
            status: JourneyStageStatus.active,
          ),
        ],
        understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '我先确认你的核心问题和约束。',
          concernPoints: <String>['先看事实', '再看建议'],
          queryDesignSummary: '我会先按关键信号拆开检索。',
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
          queryGroups: <RunArtifactsUnderstandingQueryGroup>[
            RunArtifactsUnderstandingQueryGroup(
              dimension: '市场异动',
              queries: <String>['昨天A股 大涨 原因', '昨日 A股 涨停 板块'],
              why: '先确认对应交易日的主线和板块扩散。',
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
      expect(state.process.blocks.length, 6);
      expect(state.process.blocks.first.title, '我先确认你的核心问题和约束。');
      expect(
        state.process.blocks.any(
          (block) =>
              block.blockId == 'understanding_resolution_items' &&
              block.items.any((item) => item.body.contains('深圳')),
        ),
        isTrue,
      );
      expect(
        state.process.blocks.any(
          (block) =>
              block.kind == ProcessDisplayBlockKind.points &&
              block.stepId == ProcessStepId.retrievalProcessing &&
              block.items.any(
                (item) =>
                    item.title == '检索设计' && item.body.contains('我会先按关键信号拆开检索。'),
              ),
        ),
        isTrue,
      );
      expect(
        state.process.blocks.any(
          (block) => block.kind == ProcessDisplayBlockKind.points,
        ),
        isTrue,
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

    test('显式 answer blocks 缺少日期锚点时，会补回 markdown 成答内容', () {
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

      expect(state.answer.blocks.length, 2);
      expect(
        renderAnswerBlocksToPlainText(state.answer.blocks),
        contains('2026-04-10'),
      );
    });

    test('显式 process blocks 只有局部时，不再从 queryGroups 回填 retrieval query design', () {
      final state = buildAssistantDisplayState(
        explicitState: const AssistantDisplayState(
          process: AssistantProcessDisplayState(
            blocks: <AssistantProcessDisplayBlock>[
              AssistantProcessDisplayBlock(
                blockId: 'retrieval_summary',
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
          queryGroups: <RunArtifactsUnderstandingQueryGroup>[
            RunArtifactsUnderstandingQueryGroup(
              dimension: '交易日确认',
              queries: <String>['2026-04-07 A股 大涨 原因'],
              why: '先把相对时间落成具体日期。',
            ),
          ],
        ),
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processingSummary: '已经把可用结果筛过一轮。',
        ),
      );

      expect(
        state.process.blocks.any(
          (block) =>
              block.blockId == 'retrieval_summary' &&
              block.title.contains('对应交易日'),
        ),
        isTrue,
      );
      expect(
        state.process.blocks.any(
          (block) =>
              block.blockId == 'retrieval_query_design' &&
              block.items.any(
                (item) =>
                    item.title == '检索设计' &&
                    item.body.contains('2026-04-07 A股 大涨 原因'),
              ),
        ),
        isFalse,
      );
    });

    test('query design 与已有总结重复时会跳过额外展示块', () {
      final state = buildAssistantDisplayState(
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
          userFacingSummary: '我会先锁定对应交易日，再核对市场主线。',
          queryDesignSummary: '我会先锁定对应交易日，再核对市场主线。',
        ),
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processingSummary: '我会先锁定对应交易日，再核对市场主线。',
        ),
      );

      expect(
        state.process.blocks.where(
          (block) => block.blockId == 'retrieval_query_design',
        ),
        isEmpty,
      );
    });
  });
}
