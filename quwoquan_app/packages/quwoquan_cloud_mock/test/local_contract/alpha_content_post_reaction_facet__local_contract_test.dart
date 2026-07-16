import 'package:test/test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test(
    'alpha Post ContentReaction 与 production Facet 保持 typed parity',
    () async {
      final reactions = AlphaContentPostReactionFacet();

      final liked = await reactions.likePost(
        LikeContentPostCommand(postId: 'post-alpha'),
      );
      final state = await reactions.getReactionState(
        GetContentPostReactionStateQuery(postId: 'post-alpha'),
      );
      final unliked = await reactions.unlikePost(
        UnlikeContentPostCommand(postId: 'post-alpha'),
      );

      expect(liked.liked, isTrue);
      expect(liked.changed, isTrue);
      expect(state.found, isTrue);
      expect(state.liked, isTrue);
      expect(unliked.liked, isFalse);
      expect(unliked.changed, isTrue);
    },
  );
}
