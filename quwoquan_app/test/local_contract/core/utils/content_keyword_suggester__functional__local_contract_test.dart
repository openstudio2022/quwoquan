import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/utils/content_keyword_suggester.dart';

void main() {
  group('屏蔽关键词候选', () {
    test('中文文本不会被错误正则切成空值', () {
      expect(suggestContentBlockedKeyword(<String>['成都周末徒步，适合新手。']), '成都周末徒步');
    });

    test('优先采用明确话题标签并去掉井号', () {
      expect(suggestContentBlockedKeyword(<String>['今天聊聊 #重复营销 内容']), '重复营销');
    });

    test('空白输入不捏造关键词', () {
      expect(suggestContentBlockedKeyword(<String>['', '  ']), isEmpty);
    });
  });
}
