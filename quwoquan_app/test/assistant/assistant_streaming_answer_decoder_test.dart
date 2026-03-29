import 'package:quwoquan_app/assistant/application/assistant_streaming_answer_decoder.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantStreamingAnswerDecoder', () {
    test('structured envelope 只输出 userMarkdown，不泄漏 JSON 前缀', () {
      final decoder = AssistantStreamingAnswerDecoder();

      expect(
        decoder.appendChunk(
          '{"contractId":"assistant_turn","decision":{"nextAction":"answer"},"messageKind":"answer","userMar',
        ),
        isEmpty,
      );

      expect(decoder.appendChunk('kdown":"深圳今天天气晴'), '深圳今天天气晴');

      expect(
        decoder.appendChunk('，适合出行。","result":{"text":"深圳今天天气晴，适合出行。"}}'),
        '，适合出行。',
      );
    });

    test('markdown 成答会直接按答案轨增量输出，不再维护 section state', () {
      final decoder = AssistantStreamingAnswerDecoder();

      expect(
        decoder.appendChunk('## 问题理解\n\n用户在比较九寨沟方向的几个周末路线。'),
        '## 问题理解\n\n用户在比较九寨沟方向的几个周末路线。',
      );
      expect(decoder.hasVisibleContent, isTrue);

      expect(decoder.appendChunk('\n\n## 关键'), '\n\n## 关键');

      expect(
        decoder.appendChunk('观点\n\n- 经典线更稳妥\n- 黄龙适合搭配首刷'),
        '观点\n\n- 经典线更稳妥\n- 黄龙适合搭配首刷',
      );

      expect(
        decoder.appendChunk('\n\n## 回答概要\n\n建议优先经典线，再按天气决定是否串黄龙。'),
        '\n\n## 回答概要\n\n建议优先经典线，再按天气决定是否串黄龙。',
      );
    });

    test('plain text answer 遇到内部字段前缀歧义时先缓冲，确认后再展示', () {
      final decoder = AssistantStreamingAnswerDecoder();

      expect(decoder.appendChunk('con'), isEmpty);
      expect(decoder.appendChunk('clusion first.'), 'conclusion first.');
    });

    test('长列表答案流式阶段会补齐标题与列表空格', () {
      final decoder = AssistantStreamingAnswerDecoder();

      expect(
        decoder.appendChunk('基于最新4天攻略，我最推荐经典环线。'),
        '基于最新4天攻略，我最推荐经典环线。',
      );

      expect(
        decoder.appendChunk(
          '###🎯 为什么这是最优选？1.时间刚好：4天3晚。2.交通便利：高铁直达。',
        ),
        '\n\n### 🎯 为什么这是最优选？\n\n1. 时间刚好：4天3晚。\n\n2. 交通便利：高铁直达。',
      );
    });
  });
}
