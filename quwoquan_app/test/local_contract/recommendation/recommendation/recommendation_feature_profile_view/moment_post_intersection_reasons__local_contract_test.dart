import 'package:flutter_test/flutter_test.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/cloud_services/content/content_post_contract_fixture.dart';

ContentPostViewData _moment({
  required String postId,
  required String body,
  List<IntersectionReason>? intersectionReasons,
}) => ContentPostViewData.fromWire(
  contentPostProjectionFixture(
    postId: postId,
    contentType: 'micro',
    contentIdentity: 'moment',
    authorId: 'u1',
    body: body,
    intersectionReasons: intersectionReasons,
  ),
);

void main() {
  group('ContentPostProjection.intersectionReasons', () {
    test('canonical wire 解析为强类型 IntersectionReason', () {
      final reason = intersectionReasonFixture(
        dimension: 'identity',
        tagRefs: const <String>['identity/campus/xdf'],
        primaryText: '你和 TA 都来自新东方校友圈',
        totalPointCount: 3,
      );
      final projection = contentPostProjectionFixture(
        postId: 'm-test',
        contentType: 'micro',
        contentIdentity: 'moment',
        body: 'hello',
        intersectionReasons: <IntersectionReason>[reason],
      );

      final decoded = ContentPostProjection.fromWire(projection.toWire());
      final view = ContentPostViewData.fromWire(decoded);

      expect(view.intersectionReasons, hasLength(1));
      expect(view.intersectionReasons!.single.dimension, 'identity');
      expect(view.intersectionReasons!.single.primaryText, '你和 TA 都来自新东方校友圈');
      expect(
        view.intersectionReasons!.single.tagRefs,
        contains('identity/campus/xdf'),
      );
    });

    test('无交集来源时为 null，内容卡不伪造理由', () {
      final view = _moment(postId: 'm-empty', body: 'hello');

      expect(view.intersectionReasons, isNull);
    });

    test('content 维度与旅行 tag 保持 canonical typed facts', () {
      final view = _moment(
        postId: 'm-travel-content',
        body: '去了趟洱海',
        intersectionReasons: <IntersectionReason>[
          intersectionReasonFixture(
            dimension: 'content',
            tagRefs: const <String>['Topic/旅行'],
            primaryText: '你和 TA 都在聊 旅行',
            totalPointCount: 12,
          ),
        ],
      );

      final reason = view.intersectionReasons!.single;
      expect(reason.dimension, 'content');
      expect(reason.tagRefs, contains('Topic/旅行'));
      expect(reason.primaryText, '你和 TA 都在聊 旅行');
    });

    test('ContentPostProjection wire 往返保留 location 交集理由', () {
      final projection = contentPostProjectionFixture(
        postId: 'm-roundtrip',
        contentType: 'micro',
        contentIdentity: 'moment',
        authorId: 'u1',
        body: '左边董宇辉右边俞敏洪',
        intersectionReasons: <IntersectionReason>[
          intersectionReasonFixture(
            dimension: 'location',
            tagRefs: const <String>['location/geo/west-lake'],
            primaryText: '你和 TA 都看过 西湖',
            totalPointCount: 5,
          ),
        ],
      );

      final decoded = ContentPostProjection.fromWire(projection.toWire());
      final view = ContentPostViewData.fromWire(decoded);

      expect(view.intersectionReasons, isNotNull);
      expect(view.intersectionReasons!.single.primaryText, '你和 TA 都看过 西湖');
      expect(view.intersectionReasons!.single.dimension, 'location');
    });

    test('generated decoder 拒绝旧 displayText 等第二字段轨', () {
      final reason = intersectionReasonFixture();
      final wire = contentPostProjectionFixture(
        postId: 'm-noncanonical-reason',
        contentType: 'micro',
        intersectionReasons: <IntersectionReason>[reason],
      ).toWire();
      final reasons = wire['intersectionReasons']! as List<Object?>;
      final noncanonicalReason = Map<String, Object?>.from(
        reasons.single! as Map,
      )..['displayText'] = 'retired alias';
      wire['intersectionReasons'] = <Object?>[noncanonicalReason];

      expect(() => ContentPostProjection.fromWire(wire), throwsFormatException);
    });
  });
}
