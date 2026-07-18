import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test(
    'alpha Post publication fixture is idempotent by publish intent',
    () async {
      final writer = AlphaContentPostPublicationWriter();
      final command = SubmitContentPostPublicationCommand(
        publishIntentId: 'publish-draft-1',
        localDraftId: 'draft-1',
        contentType: ContentPostType.micro,
        body: 'alpha typed post',
        visibility: ContentPostVisibility.public,
      );
      final published = await writer.submitPostPublication(command);
      final replayed = await writer.submitPostPublication(command);

      expect(published.postId, isNotEmpty);
      expect(replayed.postId, published.postId);
      expect(replayed.publishIntentId, command.publishIntentId);
    },
  );
}
