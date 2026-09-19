// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/alpha_post_intersection_projector.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  Map<String, Object?> post(String author) => <String, Object?>{
    'postId': 'post-alpha',
    'authorId': author,
    'contentType': 'image',
    'contentIdentity': 'work',
    'title': '雪山路线',
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
  };

  test('当前 viewer 的关系和点赞事实确定性投影完整 canonical reason', () async {
    final store = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    await store.commit(() {
      store.follows[store.followKey(
        'viewer-a',
        'friend-a',
      )] = <String, Object?>{
        'actorPersonaId': 'viewer-a',
        'targetPersonaId': 'friend-a',
        'active': true,
      };
      store.reactions[store.reactionKey(
        'friend-a',
        'post-alpha',
      )] = <String, Object?>{
        'actorId': 'friend-a',
        'postId': 'post-alpha',
        'liked': true,
      };
    });
    final wire = const AlphaPostIntersectionProjector().project(
      post: post('creator-a'),
      viewerId: 'viewer-a',
      store: store,
      now: DateTime.utc(2026, 9, 13),
    );
    final decoded = ContentPostProjection.fromWire(wire);
    final reason = decoded.intersectionReasons!.single;
    expect(reason.subjectId, 'viewer-a');
    expect(reason.subjectContext, 'post:post-alpha');
    expect(reason.actionTargetId, 'post-alpha');
    expect(
      reason.primarySpans.map((span) => span.text).join(),
      reason.primaryText,
    );
    expect(reason.intersectionPoints, isNotEmpty);
    expect(reason.evidenceRows, isNotEmpty);
  });

  test('无事实与切换 viewer 均不泄露私有交集', () async {
    final store = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    await store.commit(() {
      store.follows[store.followKey(
        'viewer-a',
        'friend-a',
      )] = <String, Object?>{
        'actorPersonaId': 'viewer-a',
        'targetPersonaId': 'friend-a',
        'active': true,
      };
      store.reactions[store.reactionKey(
        'friend-a',
        'post-alpha',
      )] = <String, Object?>{
        'actorId': 'friend-a',
        'postId': 'post-alpha',
        'liked': true,
      };
    });
    final projector = const AlphaPostIntersectionProjector();
    expect(
      projector
          .project(
            post: post('creator-a'),
            viewerId: 'viewer-b',
            store: store,
            now: DateTime.utc(2026),
          )
          .containsKey('intersectionReasons'),
      isFalse,
    );
    store.follows[store.followKey('viewer-a', 'friend-a')]!['active'] = false;
    expect(
      projector
          .project(
            post: post('creator-a'),
            viewerId: 'viewer-a',
            store: store,
            now: DateTime.utc(2026),
          )
          .containsKey('intersectionReasons'),
      isFalse,
    );
  });

  test('作品作者身份保持 bundle author，不冒充当前 viewer', () {
    final store = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    final wire = const AlphaPostIntersectionProjector().project(
      post: post('creator-a'),
      viewerId: 'viewer-a',
      store: store,
      now: DateTime.utc(2026),
    );
    expect(wire['authorId'], 'creator-a');
    expect(wire['authorId'], isNot('viewer-a'));
  });
}
