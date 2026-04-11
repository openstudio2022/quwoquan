import 'dart:convert';

import 'package:quwoquan_app/assistant/tool/impl/web/normalized_web_reference.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:test/test.dart';

void main() {
  group('NormalizedWebReference vendor fixtures', () {
    test('SerpAPI organic uses link as url (matches legacy extraction)', () {
      final item = <String, dynamic>{
        'title': ' Example ',
        'link': ' https://a.test/x ',
        'snippet': ' Snip ',
      };
      final n = NormalizedWebReference.fromSerpApiOrganic(item);
      expect(n.title, 'Example');
      expect(n.url, 'https://a.test/x');
      expect(n.snippet, 'Snip');
      expect(n.coreMap['url'], n.url);
    });

    test('DuckDuckGo RelatedTopics uses Text/FirstURL', () {
      final item = <String, dynamic>{
        'Text': ' Hello ',
        'FirstURL': ' https://b.test/y ',
      };
      final n = NormalizedWebReference.fromDuckduckgoRelatedTopic(item);
      expect(n.title, 'Hello');
      expect(n.url, 'https://b.test/y');
      expect(n.snippet, 'Hello');
    });

    test('fixture JSON decodes to stable triples', () {
      const serpFixture = '''
{"organic_results":[{"title":"T","link":"https://u","snippet":"S"}]}
''';
      final root =
          jsonDecode(serpFixture) as Map<String, dynamic>;
      final organic = (root['organic_results'] as List).cast<Map<String, dynamic>>();
      final n = NormalizedWebReference.fromSerpApiOrganic(organic.first);
      expect(n.isUsable, isTrue);
      expect(n.url, 'https://u');
    });
  });

  group('WebSearchTool provider JSON → _extractReferences', () {
    final tool = WebSearchTool(
      resolveRuntimeConfigFromDisk: false,
      enableInteractionLogging: false,
    );

    test('Brave minimal web.results fixture', () {
      final decoded = jsonDecode('''
{"web":{"results":[
  {"title":" BT ","url":" https://brave.test/x ","description":" D "}
]}}
''') as Map<String, dynamic>;
      final refs = tool.extractReferencesForFixtureTest(
        provider: AssistantSearchProvider.brave,
        decoded: decoded,
      );
      expect(refs.length, 1);
      expect(refs.first['provider'], 'brave');
      expect(refs.first['title'], 'BT');
      expect(refs.first['url'], 'https://brave.test/x');
      expect(refs.first['snippet'], 'D');
    });

    test('Perplexity citations fixture', () {
      final decoded = jsonDecode('''
{"citations":[" https://p.test/a ",""," https://p.test/b "]}
''') as Map<String, dynamic>;
      final refs = tool.extractReferencesForFixtureTest(
        provider: AssistantSearchProvider.perplexity,
        decoded: decoded,
      );
      expect(refs.length, 2);
      for (final r in refs) {
        expect(r['provider'], 'perplexity');
        expect(r['title'], r['url']);
        expect(r['snippet'], '');
      }
      expect(refs.first['url'], 'https://p.test/a');
      expect(refs[1]['url'], 'https://p.test/b');
    });

    test('Openclaw references fixture', () {
      final decoded = jsonDecode('''
{"references":[
  {"title":" OC ","url":" https://oc.test/z ","snippet":" S "}
]}
''') as Map<String, dynamic>;
      final refs = tool.extractReferencesForFixtureTest(
        provider: AssistantSearchProvider.openclawProxy,
        decoded: decoded,
      );
      expect(refs.length, 1);
      expect(refs.first['provider'], 'openclawProxy');
      expect(refs.first['title'], 'OC');
      expect(refs.first['url'], 'https://oc.test/z');
      expect(refs.first['snippet'], 'S');
    });
  });
}
