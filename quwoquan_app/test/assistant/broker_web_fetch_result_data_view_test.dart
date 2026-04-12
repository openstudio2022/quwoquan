import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:test/test.dart';

void main() {
  group('BrokerWebFetchResultDataView', () {
    test('reads referenceMaps and string getters', () {
      final view = BrokerWebFetchResultDataView(<String, dynamic>{
        'url': ' https://a.test ',
        'title': ' T ',
        'summary': ' S ',
        'references': <Map<String, dynamic>>[
          <String, dynamic>{'url': 'https://ref', 'snippet': ' snip '},
        ],
      });
      expect(view.referenceMaps.length, 1);
      expect(view.url, 'https://a.test');
      expect(view.title, 'T');
      expect(view.summary, 'S');
      expect(view.raw['summary'], ' S ');
    });

    test('content passes through', () {
      final view = BrokerWebFetchResultDataView(<String, dynamic>{
        'content': 'body',
      });
      expect(view.content, 'body');
    });
  });
}
