import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

void main() {
  group('SafeReferenceNormalizer', () {
    test('unwraps redirect url and strips tracking params', () {
      final canonicalUrl = SafeReferenceNormalizer.canonicalizeUrl(
        'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.cma.cn%2Fshenzhen%3Futm_source%3Dfeed%26fbclid%3Dabc',
      );

      expect(canonicalUrl, equals('https://weather.cma.cn/shenzhen'));
    });

    test('normalizes garbled title, html entities and source fallback', () {
      final normalized = SafeReferenceNormalizer.normalize(<String, dynamic>{
        'title': 'Ã¤Â¸Â­å›½å¤©æ°”',
        'url': 'https://weather.cma.cn/forecast?utm_campaign=spring',
        'snippet': 'Tom&nbsp;&amp;&nbsp;Jerry',
        'source': '',
      });

      expect(normalized, isNotNull);
      expect(normalized!['url'], equals('https://weather.cma.cn/forecast'));
      expect(normalized['title'], equals('weather.cma.cn forecast'));
      expect(normalized['snippet'], equals('Tom & Jerry'));
      expect(normalized['source'], equals('weather.cma.cn'));
      expect(normalized['sourceHost'], equals('weather.cma.cn'));
    });
  });
}
