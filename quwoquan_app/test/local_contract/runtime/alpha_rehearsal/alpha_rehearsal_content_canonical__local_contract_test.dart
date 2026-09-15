// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/content_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/runtime/config/runtime_package_test_hydration.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  installCanonicalOfflineAssetsForTests();

  const handler = ContentRehearsalHandler(postExists: bundledPostExists);
  var sequence = 0;
  final now = DateTime.utc(2026, 9, 13, 12);
  const alice = CloudOperationInvocationContext(
    surfaceId: 'rehearsal',
    clientPageId: 'rehearsal',
    actor: CloudOperationActorContext(
      accountId: 'account-a',
      personaId: 'alice',
    ),
  );
  const bob = CloudOperationInvocationContext(
    surfaceId: 'rehearsal',
    clientPageId: 'rehearsal',
    actor: CloudOperationActorContext(accountId: 'account-b', personaId: 'bob'),
  );

  Future<Object?> invoke(
    AlphaRehearsalStore store,
    String operation, {
    CloudOperationInvocationContext context = alice,
    Map<String, String> path = const {},
    Map<String, String> query = const {},
    Map<String, Object?> body = const {},
  }) => handler.handle(
    RehearsalInvocation(
      operation: appCloudOperationContracts[operation]!,
      payload: CloudOperationRequestPayload(
        pathParameters: path,
        queryParameters: query,
        body: body,
      ),
      context: context,
      store: store,
      now: () => now,
      nextId: (prefix) => '$prefix${sequence++}',
    ),
  );

  test('能力 inventory 对目标 content 域完整分区且上传明确 unsupported', () {
    final targeted = appCloudOperationContracts.keys.where(
      (id) => const [
        'content.comment.',
        'content.content_behavior_fact.',
        'content.content_reaction.',
        'content.media_asset.',
        'content.media_upload_session.',
        'content.outbound_share_fact.',
        'content.post.',
        'content.post_collection.',
        'content.profile_interaction_activity_view.',
        'content.profile_interaction_read_fact.',
        'content.report.',
      ].any(id.startsWith),
    );
    expect(
      targeted.toSet().difference({
        ...alphaContentSupportedOperations,
        ...alphaContentUnsupportedOperations,
      }),
      isEmpty,
    );
    expect(
      alphaContentSupportedOperations.intersection(
        alphaContentUnsupportedOperations,
      ),
      isEmpty,
    );
    expect(
      () => invoke(
        AlphaRehearsalStore(persistence: MemoryRehearsalPersistence()),
        'content.media_upload_session.InitMediaUpload',
      ),
      throwsA(isA<CloudException>()),
    );
  });

  test('默认存在性只接受 store canonical target，不依赖 bundle', () async {
    const storeOnlyHandler = ContentRehearsalHandler();
    final store = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    Future<Object?> like(String postId) => storeOnlyHandler.handle(
      RehearsalInvocation(
        operation:
            appCloudOperationContracts['content.content_reaction.LikePost']!,
        payload: CloudOperationRequestPayload(
          pathParameters: <String, String>{'postId': postId},
        ),
        context: alice,
        store: store,
        now: () => now,
        nextId: (prefix) => '$prefix${sequence++}',
      ),
    );

    await expectLater(
      like('unknown-post'),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          'CONTENT.USER.content_reaction_target_not_found',
        ),
      ),
    );
    store.records['content.local_posts'] = {
      'post-1': {'postId': 'post-1'},
    };
    expect(await like('post-1'), isA<Map<String, Object?>>());
  });

  test('canonical post/feed/media 读取 OfflineContentBundle 而非默认 wire', () async {
    final store = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    final bundle = await OfflineContentBundle.load();
    final detail = Map<String, Object?>.from(
      bundle.rows('posts').first['detail']! as Map,
    );
    final postId = detail['postId']! as String;
    final post = await invoke(
      store,
      'content.post.GetPost',
      path: {'postId': postId},
    ) as Map<String, Object?>;
    expect(post['title'], detail['title']);
    expect(post['intersectionReasons'], isNot(isA<Map>()));
    expect(post.containsKey('postAssociationSummary'), isFalse);

    final feed = await invoke(
      store,
      'content.post.GetFeed',
      query: {'limit': '1', 'channelId': 'recommend'},
    ) as Map<String, Object?>;
    expect(feed['items'], hasLength(1));
    expect(feed['nextCursor'], isNotEmpty);

    final mediaId = bundle.rows('media').first['assetId']! as String;
    final media = await invoke(
      store,
      'content.media_asset.GetMediaAsset',
      path: {'mediaId': mediaId},
    ) as Map<String, Object?>;
    expect(media['assetId'], mediaId);
    expect(media['fileSize'], greaterThan(0));
  });

  test('评论分页、权限、删除及持久化重启可验证', () async {
    final persistence = MemoryRehearsalPersistence();
    var store = AlphaRehearsalStore(persistence: persistence);
    final postId = (await OfflineContentBundle.load())
        .rows('posts')
        .first['detail']
        .let((value) => (value as Map)['postId'] as String);
    final ids = <String>[];
    for (final text in ['一', '二', '三']) {
      final result = await invoke(
        store,
        'content.comment.CreateComment',
        path: {'postId': postId},
        body: {'content': text},
      ) as Map<String, Object?>;
      ids.add(result['id']! as String);
    }
    final first = await invoke(
      store,
      'content.comment.ListComments',
      path: {'postId': postId},
      query: {'limit': '2', 'sort': 'newest'},
    ) as Map<String, Object?>;
    expect(first['items'], hasLength(2));
    expect(first['nextCursor'], isNotEmpty);

    await expectLater(
      invoke(
        store,
        'content.comment.DeleteComment',
        context: bob,
        path: {'postId': postId, 'commentId': ids.first},
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          'CONTENT.USER.comment_forbidden_delete',
        ),
      ),
    );

    await invoke(
      store,
      'content.comment.DeleteComment',
      path: {'postId': postId, 'commentId': ids.first},
    );
    store = AlphaRehearsalStore(persistence: persistence);
    await store.ensureLoaded();
    final afterRestart = await invoke(
      store,
      'content.comment.ListComments',
      path: {'postId': postId},
      query: {'limit': '20', 'sort': 'newest'},
    ) as Map<String, Object?>;
    expect(afterRestart['total'], 2);
  });

  test('行为、合集、举报写入 store 并在重启后读回', () async {
    final persistence = MemoryRehearsalPersistence();
    var store = AlphaRehearsalStore(persistence: persistence);
    final post = Map<String, Object?>.from(
      (await OfflineContentBundle.load()).rows('posts').first['detail']! as Map,
    );
    final postId = post['postId']! as String;
    final behavior = await invoke(
      store,
      'content.content_behavior_fact.ReportBehaviors',
      body: {
        'events': [
          {
            'eventId': 'behavior-1',
            'postId': postId,
            'type': 'view',
            'occurredAt': now.toIso8601String(),
          },
        ],
      },
    ) as Map<String, Object?>;
    expect(behavior['acceptedCount'], 1);
    final replay = await invoke(
      store,
      'content.content_behavior_fact.ReportBehaviors',
      body: {
        'events': [
          {'eventId': 'behavior-1', 'postId': postId, 'type': 'view'},
        ],
      },
    ) as Map<String, Object?>;
    expect(replay['replayedCount'], 1);

    await invoke(
      store,
      'content.post_collection.SavePostCollection',
      path: {'collectionId': 'collection-1'},
      body: {
        'expectedVersion': 0,
        'name': '本地合集',
        'visibility': 'private',
        'postIds': [postId],
      },
    );
    await invoke(
      store,
      'content.report.CreateReport',
      body: {'targetId': postId, 'targetType': 'post', 'reason': 'spam'},
    );

    store = AlphaRehearsalStore(persistence: persistence);
    await store.ensureLoaded();
    final management = await invoke(
      store,
      'content.post_collection.GetPostCollectionManagement',
      body: {
        'variables': {'collectionId': 'collection-1'},
      },
    ) as Map<String, Object?>;
    expect(management['name'], '本地合集');
    final reports = await invoke(
      store,
      'content.report.ListMyReports',
      query: {'limit': '20'},
    ) as Map<String, Object?>;
    expect(reports['items'], hasLength(1));
    final footprint = await invoke(
      store,
      'content.post.GetMyFootprint',
      query: {'limit': '20'},
    ) as Map<String, Object?>;
    expect(footprint['items'], hasLength(1));
  });
}

extension _Let<T> on T {
  R let<R>(R Function(T value) transform) => transform(this);
}
