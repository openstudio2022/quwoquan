import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';

void main() {
  testWidgets('iPad 成答失败不会把 assistant_turn JSON 展示为最终答案', (tester) async {
    const internalEnvelope =
        '{"contractId":"assistant_turn","decision":{"nextAction":"abort"},'
        '"messageKind":"fallback","userMarkdown":"",'
        '"result":{"interpretation":"answer_organization_failed"}}';

    final state = buildAssistantDisplayState(answerMarkdown: internalEnvelope);
    final answerMarkdown = renderAnswerBlocksToMarkdown(state.answer.blocks);

    expect(answerMarkdown, isEmpty);
    expect(state.answer.blocks, isEmpty);
  });
}
