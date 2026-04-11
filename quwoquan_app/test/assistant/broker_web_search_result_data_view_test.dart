import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:test/test.dart';

void main() {
  group('BrokerWebSearchResultDataView', () {
    test('reads embedded references and summaryOrSnippet', () {
      final view = BrokerWebSearchResultDataView(<String, dynamic>{
        'references': <Map<String, dynamic>>[
          <String, dynamic>{'title': 'A', 'url': 'https://a.test'},
        ],
        'summary': ' S ',
        'snippet': 'ignored',
      });
      expect(view.embeddedReferences.length, 1);
      expect(view.embeddedReferences.first['url'], 'https://a.test');
      expect(view.summaryOrSnippet, 'S');
      expect(view.raw['snippet'], 'ignored');
    });

    test('summaryOrSnippet falls back to snippet', () {
      final view = BrokerWebSearchResultDataView(<String, dynamic>{
        'snippet': ' body ',
      });
      expect(view.summaryOrSnippet, 'body');
    });

    test('valueOf trims string fields', () {
      final view = BrokerWebSearchResultDataView(<String, dynamic>{
        'title': '  t  ',
        'url': ' https://u ',
      });
      expect(view.valueOf('title'), 't');
      expect(view.valueOf('url'), 'https://u');
    });
  });
}
