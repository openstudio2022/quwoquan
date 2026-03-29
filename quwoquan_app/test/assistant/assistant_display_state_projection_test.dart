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
      expect(state.process.blocks.length, 4);
      expect(state.process.blocks.first.title, '我先确认你的核心问题和约束。');
      expect(
        state.process.blocks.any(
          (block) => block.kind == ProcessDisplayBlockKind.points,
        ),
        isFalse,
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
  });
}
