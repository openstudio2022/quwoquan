import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void main() {
  group('client state sync outbox', () {
    test('同一 profile follow 意图会按 latest_wins 合并', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueueFollow(
        profileSubjectId: 'profile-1',
        shouldFollow: true,
      );
      notifier.enqueueFollow(
        profileSubjectId: 'profile-1',
        shouldFollow: false,
      );

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 1);
      expect(state.entries.single.desiredBoolValue, isFalse);
    });

    test('同一 post 的 like/save 意图分别独立合并', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueuePostLike(postId: 'post-1', isLiked: true);
      notifier.enqueuePostLike(postId: 'post-1', isLiked: false);
      notifier.enqueuePostSave(postId: 'post-1', isSaved: true);

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 2);
      expect(
        state.entries
            .where((entry) => entry.objectId == 'post-1' && entry.intentType == 'like')
            .single
            .desiredBoolValue,
        isFalse,
      );
      expect(
        state.entries
            .where((entry) => entry.objectId == 'post-1' && entry.intentType == 'save')
            .single
            .desiredBoolValue,
        isTrue,
      );
    });
  });
}
