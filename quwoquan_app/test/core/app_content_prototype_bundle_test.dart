import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_prototype_codec.dart';

void main() {
  group('AppContentPrototypeBundle', () {
    test('解码后聊天/圈子原型非空且为强类型', () {
      final b = AppContentPrototypeBundle.instance;
      expect(b.chatEncryptedConversations, isNotEmpty);
      expect(b.chatEncryptedConversations.first.id, isNotEmpty);
      expect(b.circlesMockCircles, isNotEmpty);
      expect(b.circlesMockCircles.first.id, isNotEmpty);
      expect(b.circlesCategoryConfig.containsKey('all'), isTrue);
      expect(b.helperReadSummary.oneLiner, isNotEmpty);
    });
  });
}
