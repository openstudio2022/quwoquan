import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

void main() {
  group('SafeReferenceNormalizer', () {
    test('normalizeSnippet strips phone-like contact snippets', () {
      final snippet = SafeReferenceNormalizer.normalizeSnippet(
        '7天时间，让我们跟着海拔起伏探索川西的极致风光，强烈推荐联系本地向导小月（电话130 3281 2978）。',
      );

      expect(snippet, isEmpty);
    });

    test('normalizeFact truncates long marketing copy to short evidence', () {
      final fact = SafeReferenceNormalizer.normalizeFact(
        '交通方面，我们选了舒适的旅游大巴，司机经验丰富，路况平稳；住宿是干净的家庭房，每晚都有空调，确保宝宝睡得好；餐饮包含早餐和部分午餐，多以清淡川菜为主。',
      );

      expect(fact, isNotEmpty);
      expect(fact.length, lessThanOrEqualTo(99));
      expect(fact, isNot(contains('早餐和部分午餐')));
    });

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
