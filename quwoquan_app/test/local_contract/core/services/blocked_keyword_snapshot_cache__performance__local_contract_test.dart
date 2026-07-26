import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/services/blocked_keyword_snapshot_cache.dart';

void main() {
  test('屏蔽关键词快照缓存合并并发读取，写后立即替换', () async {
    var now = DateTime.utc(2026, 7, 20);
    var loads = 0;
    final cache = BlockedKeywordSnapshotCache(
      ttl: const Duration(minutes: 5),
      now: () => now,
    );

    Future<List<String>> loader() async {
      loads += 1;
      return <String>['广告'];
    }

    final pages = await Future.wait(<Future<List<String>>>[
      cache.load(loader),
      cache.load(loader),
    ]);
    expect(loads, 1);
    expect(pages, everyElement(<String>['广告']));

    cache.replace(<String>['剧透']);
    expect(await cache.load(loader), <String>['剧透']);
    expect(loads, 1);

    now = now.add(const Duration(minutes: 6));
    expect(await cache.load(loader), <String>['广告']);
    expect(loads, 2);
  });
}
