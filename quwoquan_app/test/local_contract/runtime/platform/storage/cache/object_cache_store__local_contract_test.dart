// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/object_cache_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ObjectCacheStore', () {
    test('maxMemoryEntries constrains the only in-memory object LRU', () {
      final store = ObjectCacheStore<String>(maxMemoryEntries: 1);

      store.put('post_1', 'one');
      store.put('post_2', 'two');

      expect(store.count, 1);
      expect(store.get('post_1'), isNull);
      expect(store.get('post_2')?.source, CacheReadSource.memory);
    });
  });
}
