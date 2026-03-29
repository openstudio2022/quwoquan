import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantDisplayTextResolver', () {
    test('completed markdown 会做通用标题与换行收敛', () {
      const raw =
          '先给结论。'
          '###核心判断1. 先核对事实2. 再整理答案';

      final normalized =
          AssistantDisplayTextResolver.stabilizeFinalAnswerMarkdown(raw);

      expect(normalized, isNot(contains('###')));
      expect(normalized, contains('先给结论。\n'));
      expect(normalized, contains('**核心判断1. 先核对事实2. 再整理答案**'));
    });

    test('streaming markdown 只做保守结构补空格与换行', () {
      const raw = '先给结论。###核心判断1.先核对事实2.再整理答案';

      final normalized =
          AssistantDisplayTextResolver.stabilizeStreamingMarkdownCandidate(raw);

      expect(normalized, contains('。\n\n### 核心判断'));
      expect(normalized, contains('### 核心判断1.先核对事实2.再整理答案'));
      expect(normalized, contains('###'));
    });

    test('completed markdown 统一经过 leaf markdown 稳定化', () {
      const raw = '先给结论。###核心判断1.先核对事实2.再整理答案';

      expect(
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw),
        AssistantDisplayTextResolver.stabilizeFinalAnswerMarkdown(
          AssistantDisplayTextResolver.normalizeMarkdown(raw),
        ),
      );
    });
  });
}
