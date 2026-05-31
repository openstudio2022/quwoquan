import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/components/object_page/tag_intersection_mapper.dart';

void main() {
  group('sharedTagsToReasons', () {
    test('透传 label 为 displayText（不本地拼装，G2）并按 group 映射 dimension', () {
      final reasons = sharedTagsToReasons(const [
        SharedTagView(tagRef: 'Topic/摄影', label: '摄影', strength: 0.8, source: 'tagRef'),
        SharedTagView(
          tagRef: 'Entity/机构/学校/北京大学',
          label: '北京大学',
          strength: 0.9,
          source: 'entityRef',
        ),
      ]);
      expect(reasons.length, 2);
      expect(reasons[0].displayText, '摄影');
      expect(reasons[0].dimension, 'interest');
      expect(reasons[0].tagRefs, ['Topic/摄影']);
      expect(reasons[0].source, 'tagRef');
      expect(reasons[1].displayText, '北京大学');
      expect(reasons[1].dimension, 'identity');
    });

    test('过滤空 tagRef / 空 label 脏数据', () {
      final reasons = sharedTagsToReasons(const [
        SharedTagView(tagRef: '', label: '空ref', strength: 1, source: 'tagRef'),
        SharedTagView(tagRef: 'Topic/旅行', label: '', strength: 1, source: 'tagRef'),
        SharedTagView(tagRef: 'Topic/旅行', label: '旅行', strength: 1, source: 'tagRef'),
      ]);
      expect(reasons.length, 1);
      expect(reasons.single.tagRefs, ['Topic/旅行']);
    });

    test('Format→content、Audience→identity、未知→interest', () {
      expect(dimensionForTagRef('Format/内容载体'), 'content');
      expect(dimensionForTagRef('Audience/学生'), 'identity');
      expect(dimensionForTagRef('Unknown/x'), 'interest');
    });

    test('空输入返回空列表', () {
      expect(sharedTagsToReasons(const []), isEmpty);
    });
  });
}
