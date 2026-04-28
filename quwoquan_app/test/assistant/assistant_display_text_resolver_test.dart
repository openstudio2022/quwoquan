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

    test('completed markdown 不会把 GFM 表格分隔行误拆成列表', () {
      const raw =
          '对比如下：\n'
          '\n'
          '| 维度 | 华为云 | 阿里云 | 腾讯云 |\n'
          '| :--- | :--- | :--- | :--- |\n'
          '| 核心优势 | 算力强 | 生态成熟 | 社交生态强 |\n';

      final normalized =
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);

      expect(normalized, contains('| :--- | :--- | :--- | :--- |'));
      expect(normalized, isNot(contains('| :\n- -- |')));
    });

    test('completed markdown 不会把小数点误当成编号列表', () {
      const raw =
          '**收盘数据：**\n'
          '- 上证指数：3288.41点，下跌0.20%\n'
          '- 深证成指：9855.20点，下跌0.62%\n';

      final normalized =
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);

      expect(normalized, contains('上证指数：3288.41点，下跌0.20%'));
      expect(normalized, contains('深证成指：9855.20点，下跌0.62%'));
      expect(normalized, isNot(contains('上证指数：\n\n3288.')));
    });

    test('completed markdown 会修复历史中已被误拆的小数和表格分隔行', () {
      const raw =
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
          '3288. 41点，下跌0.20%';

      final normalized =
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);

      expect(normalized, contains('| :--- | :--- | :--- | :--- |'));
      expect(normalized, contains('上证指数：3288.41点，下跌0.20%'));
    });

    test('process narration 不再因自然语言片段被过滤', () {
      const raw = '我已经处理了检索结果，收拢到可回答的证据。';

      expect(
        AssistantDisplayTextResolver.normalizeUserFacingProcessNarration(raw),
        raw,
      );
      expect(
        AssistantDisplayTextResolver.containsInternalProcessFragment(raw),
        isFalse,
      );
    });
  });
}
