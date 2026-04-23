import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/prompt_template/runtime/prompt_snippet_renderer.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PromptSnippetRenderer', () {
    test('renders a named snippet from shared asset bundle', () async {
      final renderer = PromptSnippetRenderer(
        seededSnippets: <String, String>{
          'synthesis_anchor_reminder':
              '这轮最终回答必须显式保留至少一个主题锚点：{{anchors}}。',
        },
      );
      final rendered = await renderer.renderSnippet(
        'synthesis_anchor_reminder',
        variables: <String, dynamic>{'anchors': '深圳、天气'},
      );

      expect(rendered, contains('深圳、天气'));
      expect(rendered, contains('最终回答必须显式保留至少一个主题锚点'));
    });

    test('renders multi-line snippet with variables intact', () async {
      final renderer = PromptSnippetRenderer(
        seededSnippets: <String, String>{
          'subagent_execution': '''
你是后台子代理。目标是完成分配任务并给出结构化结论，禁止输出与任务无关内容。
路由叙事：{{routeNarrative}}
局部上下文：{{localContextSeed}}
''',
        },
      );
      final rendered = await renderer.renderSnippet(
        'subagent_execution',
        variables: <String, dynamic>{
          'routeNarrative': '路由叙事：先查天气',
          'localContextSeed': '局部上下文：深圳',
        },
      );

      expect(rendered, contains('路由叙事：先查天气'));
      expect(rendered, contains('局部上下文：深圳'));
      expect(rendered, contains('你是后台子代理。目标是完成分配任务并给出结构化结论'));
    });

    test(
        'global prompt_snippets: <!-- snippet:end --> 闭合片段且不被误解析为 id=end',
        () async {
      final renderer = PromptSnippetRenderer();
      final rendered = await renderer.renderSnippet('force_answer_conclusion');
      expect(rendered, isNotEmpty);
      expect(rendered, contains('decision=answer'));
    });
  });
}
