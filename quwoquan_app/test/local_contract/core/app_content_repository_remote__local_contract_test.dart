import 'package:test/test.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  group('RemoteAppContentRepository', () {
    late RemoteAppContentRepository repo;

    setUp(() {
      repo = RemoteAppContentRepository();
    });

    test('发现区四类聚合为空', () {
      expect(repo.discoveryMomentData, isEmpty);
      expect(repo.discoveryPhotoData, isEmpty);
      expect(repo.discoveryArticleData, isEmpty);
      expect(repo.discoveryVideoData, isEmpty);
    });

    test('chat / assistant 占位 getter 为空', () {
      expect(repo.chatMockContacts, isEmpty);
      expect(repo.chatMockConversations, isEmpty);
      expect(repo.assistantTasksData, isEmpty);
    });

    test('circlesCategoryConfig 至少含 all', () {
      expect(repo.circlesCategoryConfig.containsKey('all'), isTrue);
    });
  });
}
