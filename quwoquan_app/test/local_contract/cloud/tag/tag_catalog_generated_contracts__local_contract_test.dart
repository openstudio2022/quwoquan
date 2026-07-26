import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
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
        ValidateTagRefsQuery(
          expectedTaxonomyReleaseId:
              ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
          tagRefs: const ['Topic/旅行', 'Place/中国'],
        ),
      );

      expect(resolve.queryParameters, {'tagRef': 'Topic/旅行'});
      expect(children.queryParameters, {
        'parentTagRef': 'Topic/旅行',
        'limit': '30',
      });
      expect(validation.body, {
        'expectedTaxonomyReleaseId':
            ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
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
      final children = decodeTagChildrenSlice({
        'items': [
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
        ],
      });
      final validation = decodeTagValidationResult({
        'taxonomyReleaseId':
            ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
        'valid': ['Topic/旅行'],
        'invalid': ['Topic/不存在'],
      });

      expect(resolved.label, '旅行');
      expect(children.items.single.parentTagRef, 'Topic/旅行');
      expect(
        validation.taxonomyReleaseId,
        ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
      );
      expect(validation.valid, ['Topic/旅行']);
      expect(validation.invalid, ['Topic/不存在']);
    });

    test(
      'malformed Remote projections fail closed instead of synthesizing data',
      () {
        expect(
          () => decodeTagResolve({
            'data': {'tagRef': 'Topic/旅行'},
          }),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => decodeTagChildrenSlice({
            'items': [
              {
                'tagRef': 'Topic/旅行/攻略',
                'label': '攻略',
                'displayLabel': '攻略',
                'labelEn': 'Guide',
                'parentTagRef': 'Topic/旅行',
                'depth': '2',
                'hasChildren': false,
                'releaseId': 'tag-release',
                'lifecycleStatus': 'active',
              },
            ],
          }),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => decodeTagChildrenSlice(const <Object?>[]),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => decodeTagValidationResult({
            'taxonomyReleaseId': 'tag-release',
            'valid': 'Topic/旅行',
            'invalid': const <String>[],
          }),
          throwsA(isA<FormatException>()),
        );
      },
    );

    test('Tag feedback ack requires an explicit bool', () {
      expect(
        decodeTagFeedbackAck(<String, Object?>{'accepted': true}).accepted,
        isTrue,
      );
      expect(
        decodeTagFeedbackAck(<String, Object?>{'accepted': false}).accepted,
        isFalse,
      );
      expect(
        () => decodeTagFeedbackAck(<String, Object?>{}),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
