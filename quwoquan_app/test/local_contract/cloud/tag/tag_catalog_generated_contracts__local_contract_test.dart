import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// wire 编解码用例只需要一个稳定的发布号；发布身份的真相源是 tag-service，
/// 不是端侧编译常量。
const String _taxonomyReleaseId = 'tag-taxonomy-contract-fixture';

void main() {
  group('TagCatalog generated client contracts', () {
    test('encodes commercial App queries without exposing wire maps', () {
      final resolve = encodeTagTagNodeViewResolveTagGeneratedRequest(
        ResolveTagQuery(tagRef: ' Topic/旅行 '),
      );
      final children = encodeTagTagNodeViewListTagChildrenGeneratedRequest(
        ListTagChildrenQuery(parentTagRef: 'Topic/旅行', limit: 30),
      );
      final validation = encodeTagTagNodeViewValidateTagRefsGeneratedRequest(
        ValidateTagRefsQuery(
          expectedTaxonomyReleaseId:
              _taxonomyReleaseId,
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
            _taxonomyReleaseId,
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
            _taxonomyReleaseId,
        'valid': ['Topic/旅行'],
        'invalid': ['Topic/不存在'],
      });

      expect(resolved.label, '旅行');
      expect(children.items.single.parentTagRef, 'Topic/旅行');
      expect(
        validation.taxonomyReleaseId,
        _taxonomyReleaseId,
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

    test('Tag feedback action is a metadata-owned typed enum', () {
      final request = ReportTagFeedbackCommand(
        tagRef: ' Topic/旅行 ',
        action: TagFeedbackAction.correct,
      );

      expect(
        encodeTagTagFeedbackReportTagFeedbackGeneratedRequest(request).body,
        <String, Object?>{'tagRef': 'Topic/旅行', 'action': 'correct'},
      );
    });

    test('Every feedback action encodes to its own wire value', () {
      final encoded = <String>{};
      for (final action in TagFeedbackAction.values) {
        final body =
            encodeTagTagFeedbackReportTagFeedbackGeneratedRequest(
                  ReportTagFeedbackCommand(tagRef: 'Topic/旅行', action: action),
                ).body
                as Map<String, Object?>;
        expect(body['action'], action.wireValue);
        expect(encoded.add(action.wireValue), isTrue);
      }
    });

    test('Tag feedback carries a negative action, not only positive ones', () {
      // 只有 click/ignore/correct 时，用户无法把推错的标签压下去：
      // ignore 只回到无偏好，correct 不改特征。
      expect(TagFeedbackAction.values, contains(TagFeedbackAction.dislike));
      expect(
        encodeTagTagFeedbackReportTagFeedbackGeneratedRequest(
          ReportTagFeedbackCommand(
            tagRef: 'Topic/摄影/器材/无人机',
            action: TagFeedbackAction.dislike,
          ),
        ).body,
        <String, Object?>{'tagRef': 'Topic/摄影/器材/无人机', 'action': 'dislike'},
      );
    });
  });
}
