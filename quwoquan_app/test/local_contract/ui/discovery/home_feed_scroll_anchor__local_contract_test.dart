// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/content/post/domain/home_feed_scroll_anchor.dart';

HomeFeedScrollAnchor _anchor(String channelId, String identity) {
  return HomeFeedScrollAnchor(
    channelId: channelId,
    stableEntryIdentity: identity,
    entryIndex: 7,
    scrollOffset: 1280,
    viewportOffset: -24,
    capturedAt: DateTime.utc(2026, 7, 28),
  );
}

void main() {
  group('HomeFeedScrollAnchorStore', () {
    test('stable identity preserves post and absolute object-card anchor', () {
      expect(homeFeedPostEntryIdentity('post-7'), 'post:post-7');
      expect(
        homeFeedObjectCardEntryIdentity(
          objectKind: 'entity_homepage',
          objectId: 'west_lake',
          anchorIndex: 18,
        ),
        'object:entity_homepage:west_lake:18',
      );
    });

    test('LRU keeps a bounded channel set and never retains widget state', () {
      final store = HomeFeedScrollAnchorStore(maxChannels: 2);
      store.save(_anchor('recommend', 'post:r1'));
      store.save(_anchor('campus', 'post:c1'));

      expect(
        store.readRestorable(
          'recommend',
          residentEntryIdentities: const <String>{'post:r1'},
        ),
        isNotNull,
      );
      store.save(_anchor('travel', 'post:t1'));

      expect(store.channelIds, <String>['recommend', 'travel']);
      expect(store.peek('campus'), isNull);
      expect(store.count, 2);
    });

    test(
      'does not apply stale pixels when the stable item is not resident',
      () {
        final store = HomeFeedScrollAnchorStore();
        store.save(_anchor('recommend', 'post:old'));

        expect(
          store.readRestorable(
            'recommend',
            residentEntryIdentities: const <String>{'post:new'},
          ),
          isNull,
        );
        expect(store.peek('recommend'), isNotNull);
      },
    );
  });
}
