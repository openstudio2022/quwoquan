// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_cache_service.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/cache_management_service.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/user_profile_cache_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/runtime/cache/content_cache_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CacheManagementService', () {
    test('清理离线内容会删除 post/query 缓存但保留会话保护计数', () async {
      final postCache = PostObjectCacheService();
      final queryStore = ContentQuerySnapshotStore();
      final conversationCache = ConversationCacheService();
      final service = CacheManagementService(
        postCache: postCache,
        querySnapshotStore: queryStore,
        userProfileCache: UserProfileCacheService(),
        conversationCache: conversationCache,
        clearTemporaryImages: () async {},
        clearAccountScopedPersistence: () async {},
      );
      postCache.putDetail(contentCacheDetailPayloadFixture('post_1'));
      queryStore.put(
        key: 'surface=discoveryFeed&cursor=',
        items: <ContentPostViewData>[contentCachePostFixture('post_1')],
      );

      final result = await service.clear(CacheClearLevel.offlineContent);

      expect(result.objectsRemoved, 2);
      expect(result.protectedObjects, conversationCache.activeDiskCount);
      expect(service.estimateUsage().postObjects, 1);
      expect(service.estimateUsage().querySnapshots, 0);
    });

    test('账号 closed 终态清除全部内存命名空间并执行持久层清理', () async {
      SharedPreferences.setMockInitialValues(const <String, Object>{});
      final postCache = PostObjectCacheService();
      final queryStore = ContentQuerySnapshotStore();
      final userCache = UserProfileCacheService(persistToPreferences: true);
      final conversationCache = ConversationCacheService()
        ..activateNamespace('owner-a::persona-a')
        ..put(const ConversationCacheRecord(id: 'conversation-a'))
        ..activateNamespace('owner-a::persona-b')
        ..put(const ConversationCacheRecord(id: 'conversation-b'));
      var imageClearCalls = 0;
      var persistenceClearCalls = 0;
      final service = CacheManagementService(
        postCache: postCache,
        querySnapshotStore: queryStore,
        userProfileCache: userCache,
        conversationCache: conversationCache,
        clearAllRebuildableImages: () async {
          imageClearCalls += 1;
        },
        clearAccountScopedPersistence: () async {
          persistenceClearCalls += 1;
        },
      );
      postCache.putDetail(contentCacheDetailPayloadFixture('post-terminal'));
      queryStore.put(
        key: 'surface=terminal&cursor=',
        items: <ContentPostViewData>[contentCachePostFixture('post-terminal')],
      );
      userCache.put('user-terminal', <String, dynamic>{
        'userId': 'user-terminal',
      });

      await service.clearForTerminalAccountClosure();

      expect(imageClearCalls, 1);
      expect(persistenceClearCalls, 1);
      expect(service.estimateUsage().totalTrackedObjects, 0);
      expect(conversationCache.totalEntryCount, 0);
      expect(userCache.memoryCount, 0);
      expect(userCache.entryCount, 0);
      expect(
        (await SharedPreferences.getInstance()).containsKey(
          'qwq.user_profile_cache',
        ),
        isFalse,
      );
    });
  });
}
