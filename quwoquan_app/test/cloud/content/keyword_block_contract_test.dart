import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/keyword_block_repository.dart';

void main() {
  group('MockKeywordBlockRepository', () {
    test('addBlockedKeyword 去重并保留非空词', () async {
      final repo = MockKeywordBlockRepository();
      await repo.addBlockedKeyword('  摄影  ');
      await repo.addBlockedKeyword('摄影');
      await repo.addBlockedKeyword(' ');
      final keywords = await repo.getBlockedKeywords();
      expect(keywords, equals(<String>['摄影']));
    });

    test('setBlockedKeywords 归一化为唯一非空集合', () async {
      final repo = MockKeywordBlockRepository();
      await repo.setBlockedKeywords(<String>['旅行', '', '旅行', '美食']);
      final keywords = await repo.getBlockedKeywords();
      expect(keywords.toSet(), equals(<String>{'旅行', '美食'}));
    });
  });
}

