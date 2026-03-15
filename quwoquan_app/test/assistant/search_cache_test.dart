import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/runtime/search_cache.dart';

void main() {
  group('SearchResultCache', () {
    late SearchResultCache cache;

    setUp(() {
      cache = SearchResultCache(ttl: const Duration(seconds: 5), maxEntries: 3);
    });

    test('stores and retrieves entries', () {
      cache.put('深圳天气', <String, dynamic>{'summary': 'sunny'});
      final result = cache.get('深圳天气');
      expect(result, isNotNull);
      expect(result?['summary'], 'sunny');
    });

    test('normalizes keys: case and whitespace', () {
      cache.put('  深圳  天气  ', <String, dynamic>{'temp': 25});
      expect(cache.has('深圳 天气'), true);
      expect(cache.has('  深圳   天气'), true);
    });

    test('returns null for missing entries', () {
      expect(cache.get('不存在'), isNull);
      expect(cache.has('不存在'), false);
    });

    test('expires entries after TTL', () async {
      cache = SearchResultCache(
        ttl: const Duration(milliseconds: 50),
        maxEntries: 10,
      );
      cache.put('query', <String, dynamic>{'data': true});
      expect(cache.has('query'), true);

      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(cache.has('query'), false);
    });

    test('evicts oldest entries when maxEntries exceeded', () {
      cache.put('a', <String, dynamic>{'v': 1});
      cache.put('b', <String, dynamic>{'v': 2});
      cache.put('c', <String, dynamic>{'v': 3});
      expect(cache.length, 3);

      cache.put('d', <String, dynamic>{'v': 4});
      expect(cache.length, lessThanOrEqualTo(3));
      expect(cache.has('d'), true);
    });

    test('clear removes all entries', () {
      cache.put('x', <String, dynamic>{'v': 1});
      cache.put('y', <String, dynamic>{'v': 2});
      expect(cache.length, 2);

      cache.clear();
      expect(cache.length, 0);
      expect(cache.has('x'), false);
    });

    test('put overwrites existing entry', () {
      cache.put('query', <String, dynamic>{'v': 1});
      cache.put('query', <String, dynamic>{'v': 2});
      expect(cache.get('query')?['v'], 2);
      expect(cache.length, 1);
    });
  });
}
