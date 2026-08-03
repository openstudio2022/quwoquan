// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('QuerySnapshot 在写盘前拒绝超过 canonical UTF-8 上限的 Post 字段', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    const storageKey = 'qwq.content_query_snapshots.byte_admission.focused';
    final queryKey = contentFeedQueryKey(
      category: 'moment',
      cursor: null,
      sort: 'recommend',
      limit: 20,
    );
    final store = ContentQuerySnapshotStore(
      persistToPreferences: true,
      storageKey: storageKey,
      telemetrySink: const NoopCacheTelemetrySink(),
    );
    await store.ensureHydrated();
    store.put(
      key: queryKey,
      items: <ContentPostViewData>[
        _post(
          'oversized_author',
          authorId: List<String>.filled(43, '人').join(),
        ),
      ],
    );
    await store.flushPersistence();

    final persisted = (await SharedPreferences.getInstance()).getString(
      storageKey,
    );
    expect(persisted, isNot(contains('oversized_author')));

    final restored = ContentQuerySnapshotStore(
      persistToPreferences: true,
      storageKey: storageKey,
      telemetrySink: const NoopCacheTelemetrySink(),
    );
    await restored.ensureHydrated();
    expect(restored.get(queryKey), isNull);
  });
}

ContentPostViewData _post(String id, {required String authorId}) {
  return contentPostViewDataFromReadModelMap(<String, dynamic>{
    'id': id,
    'type': 'micro',
    'identity': 'moment',
    'authorId': authorId,
    'displayName': '用户一',
    'avatarUrl': '',
    'body': '缓存内容',
    'imageUrls': <String>[],
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
    'createdAt': '2026-05-19T00:00:00.000Z',
    'updatedAt': '2026-05-19T00:00:00.000Z',
  });
}
