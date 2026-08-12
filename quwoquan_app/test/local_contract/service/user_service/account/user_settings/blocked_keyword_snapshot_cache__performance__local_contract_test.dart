import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/application/blocked_keyword_snapshot_cache.dart';

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

  test('屏蔽关键词读取超时后清理 singleflight，重试会创建新读取', () async {
    final firstRead = Completer<List<String>>();
    var loads = 0;
    final cache = BlockedKeywordSnapshotCache(
      lookupDeadline: const Duration(milliseconds: 20),
    );

    await expectLater(
      cache.load(() {
        loads += 1;
        return firstRead.future;
      }),
      throwsA(isA<TimeoutException>()),
    );
    expect(loads, 1);

    final retried = await cache.load(() async {
      loads += 1;
      return <String>['剧透'];
    });
    expect(retried, <String>['剧透']);
    expect(loads, 2);
  });

  test('屏蔽关键词读取失败后清理 singleflight，成功重试仍执行隐私过滤', () async {
    var loads = 0;
    final cache = BlockedKeywordSnapshotCache();

    await expectLater(
      cache.load(() {
        loads += 1;
        throw StateError('privacy unavailable');
      }),
      throwsA(isA<StateError>()),
    );

    final retried = await cache.load(() async {
      loads += 1;
      return <String>['广告'];
    });
    expect(retried, <String>['广告']);
    expect(loads, 2);
  });
}
