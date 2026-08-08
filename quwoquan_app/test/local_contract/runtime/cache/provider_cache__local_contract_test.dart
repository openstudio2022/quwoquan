import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/cache/provider_cache.dart';

/// `lib/runtime/cache/**` 的行为契约。
///
/// 该 TTL 缓存存在的唯一理由是：autoDispose Provider 在 tab 切换 / 路由 pop /
/// 长列表回收时会被销毁再重建，若无缓存就会反复重打服务。它刻意**不使用
/// `Timer`**（`Timer` 在 FakeAsync 下会成为 pending timer 让 widget 测试失败），
/// 因此过期只能是「读取时按挂钟判定」。以下用例把这几条取舍钉成可回归的断言。
void main() {
  group('TtlCacheEntry', () {
    test('freshness is evaluated against the stored timestamp', () {
      final justNow = TtlCacheEntry<int>(7, DateTime.now());
      final stale = TtlCacheEntry<int>(
        7,
        DateTime.now().subtract(const Duration(minutes: 10)),
      );

      expect(justNow.isFresh(const Duration(minutes: 5)), isTrue);
      expect(stale.isFresh(const Duration(minutes: 5)), isFalse);
    });

    test('a zero TTL treats every entry as already expired', () {
      final entry = TtlCacheEntry<String>('v', DateTime.now());

      expect(entry.isFresh(Duration.zero), isFalse);
    });

    test('carries the stored value and timestamp unchanged', () {
      final storedAt = DateTime.utc(2026, 1, 2, 3, 4, 5);
      final entry = TtlCacheEntry<List<int>>(const <int>[1, 2], storedAt);

      expect(entry.value, const <int>[1, 2]);
      expect(entry.storedAt, storedAt);
    });
  });

  group('TtlCache', () {
    test('a key that was never written is a miss', () {
      final cache = TtlCache<String>();

      expect(cache.readFresh('absent', const Duration(minutes: 5)), isNull);
    });

    test('a fresh write is returned as a hit carrying the same value', () {
      final cache = TtlCache<String>()..write('profile:1', 'alice');

      final entry = cache.readFresh('profile:1', const Duration(minutes: 5));

      expect(entry, isNotNull);
      expect(entry!.value, 'alice');
    });

    test('keys are isolated from each other', () {
      final cache = TtlCache<int>()
        ..write('a', 1)
        ..write('b', 2);

      expect(cache.readFresh('a', const Duration(minutes: 5))!.value, 1);
      expect(cache.readFresh('b', const Duration(minutes: 5))!.value, 2);
    });

    test('writing the same key replaces the previous value', () {
      final cache = TtlCache<int>()
        ..write('counter', 1)
        ..write('counter', 2);

      expect(cache.readFresh('counter', const Duration(minutes: 5))!.value, 2);
    });

    test('an expired entry is a miss and is evicted on read', () {
      final cache = TtlCache<String>()..write('profile:1', 'alice');

      // 过期判定发生在读取时刻，因此 TTL=0 即可确定性地表达「已过期」，
      // 不需要 sleep，也不引入任何 Timer。
      expect(cache.readFresh('profile:1', Duration.zero), isNull);

      // 过期项必须被顺带清理：即使随后放宽 TTL 也不得复活，
      // 否则会把陈旧数据当作命中返回给页面。
      expect(
        cache.readFresh('profile:1', const Duration(days: 1)),
        isNull,
        reason: '过期读取必须驱逐条目，放宽 TTL 不得让陈旧值复活',
      );
    });

    test('expiring one key does not evict unrelated fresh keys', () {
      final cache = TtlCache<int>()
        ..write('stale', 1)
        ..write('fresh', 2);

      expect(cache.readFresh('stale', Duration.zero), isNull);
      expect(cache.readFresh('fresh', const Duration(days: 1))!.value, 2);
    });

    test('a re-write after expiry becomes a hit again', () {
      final cache = TtlCache<int>()..write('k', 1);
      expect(cache.readFresh('k', Duration.zero), isNull);

      cache.write('k', 42);

      expect(cache.readFresh('k', const Duration(minutes: 5))!.value, 42);
    });

    test('nullable value types keep a stored null distinguishable from a miss', () {
      final cache = TtlCache<String?>()..write('resolved-to-null', null);

      final entry = cache.readFresh(
        'resolved-to-null',
        const Duration(minutes: 5),
      );

      expect(entry, isNotNull, reason: '「查过了，结果是空」必须与「没查过」区分开');
      expect(entry!.value, isNull);
      expect(cache.readFresh('never-written', const Duration(minutes: 5)), isNull);
    });
  });
}
