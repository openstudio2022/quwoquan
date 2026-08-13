// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
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
      telemetrySink: const SilentCacheTelemetrySink(),
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
      telemetrySink: const SilentCacheTelemetrySink(),
    );
    await restored.ensureHydrated();
    expect(restored.get(queryKey), isNull);
  });
}

ContentPostViewData _post(String id, {required String authorId}) {
  return contentPostViewDataFromReadModelMap(<String, dynamic>{
    'postId': id,
    'contentType': 'micro',
    'contentIdentity': 'moment',
    'authorId': authorId,
    'authorDisplayName': '用户一',
    'authorAvatarUrl': '',
    'body': '缓存内容',
    'mediaUrls': <String>[],
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
    'createdAt': '2026-05-19T00:00:00.000Z',
    'updatedAt': '2026-05-19T00:00:00.000Z',
  });
}
