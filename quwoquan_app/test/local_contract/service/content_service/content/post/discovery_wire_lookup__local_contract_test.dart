import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';

import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

void main() {
  group('InMemoryContentPostStore typed lookup', () {
    test('按 canonical postId 返回同一个 typed 对象', () {
      final post = contentPostViewDataBuilder(
        postId: 'fixture_photo_001',
        contentType: 'image',
        mediaUrls: const <String>[testContentImageUrl],
      );
      final store = InMemoryContentPostStore(
        posts: <ContentPostViewData>[post],
      );

      expect(store.postById('fixture_photo_001'), same(post));
    });

    test('未知 postId 明确返回 null，不合成 fallback Map', () {
      final store = InMemoryContentPostStore();

      expect(store.postById('missing-post'), isNull);
    });
  });
}
