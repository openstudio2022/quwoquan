import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('TagCatalog generated client contracts', () {
    test('encodes commercial App queries without exposing wire maps', () {
      final resolve = encodeResolveTagQuery(
        ResolveTagQuery(tagRef: ' Topic/旅行 '),
      );
      final children = encodeListTagChildrenQuery(
        ListTagChildrenQuery(parentTagRef: 'Topic/旅行', limit: 30),
      );
      final validation = encodeValidateTagRefsQuery(
        ValidateTagRefsQuery(tagRefs: const ['Topic/旅行', 'Place/中国']),
      );

      expect(resolve.queryParameters, {'tagRef': 'Topic/旅行'});
      expect(children.queryParameters, {
        'parentTagRef': 'Topic/旅行',
        'limit': '30',
      });
      expect(validation.body, {
        'tagRefs': ['Topic/旅行', 'Place/中国'],
      });
    });

    test('decodes resolve, children and validation responses', () {
      final resolved = decodeTagResolve({
        'data': {
          'tagRef': 'Topic/旅行',
          'group': 'Topic',
          'label': '旅行',
          'labelEn': 'Travel',
          'aliases': '',
          'ancestors': '',
        },
      });
      final children = decodeTagChildrenSlice([
        {
          'tagRef': 'Topic/旅行/攻略',
          'label': '攻略',
          'displayLabel': '攻略',
          'labelEn': 'Guide',
          'parentTagRef': 'Topic/旅行',
          'depth': 2,
          'hasChildren': false,
          'releaseId': 'tag-release',
          'lifecycleStatus': 'active',
        },
      ]);
      final validation = decodeTagValidationResult({
        'valid': ['Topic/旅行'],
        'invalid': ['Topic/不存在'],
        'suggestions': <Object?>[],
      });

      expect(resolved.label, '旅行');
      expect(children.items.single.parentTagRef, 'Topic/旅行');
      expect(validation.valid, ['Topic/旅行']);
      expect(validation.invalid, ['Topic/不存在']);
    });
  });
}
