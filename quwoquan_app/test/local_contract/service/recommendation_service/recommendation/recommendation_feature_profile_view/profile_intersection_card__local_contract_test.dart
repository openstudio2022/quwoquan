import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_statement_row.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// 交集卡真闭环（V5/S5）契约：
/// - 无交集（reasons 空 / displayText 全空）→ fromReasons 返回 null，不占位。
/// - onReasonTap 回调携带被点 IntersectionReason，dimension/tagRefs 完整可用于 BehaviorEvent 归因。
void main() {
  IntersectionReason reason({
    required String dimension,
    required List<String> tagRefs,
    required String primaryText,
  }) {
    return intersectionReasonFixture(
      dimension: dimension,
      tagRefs: tagRefs,
      primaryText: primaryText,
      objectKind: 'entity',
      actionTargetId: 'homepage_topic_photo',
      primarySpans: primaryText.trim().isEmpty
          ? const <IntersectionTextSpan>[]
          : <IntersectionTextSpan>[
              IntersectionTextSpan(text: '你们都喜欢 ', role: 'plain'),
              IntersectionTextSpan(
                text: '摄影',
                role: 'object',
                target: IntersectionTarget(
                  objectType: 'homepage',
                  objectId: 'homepage_topic_photo',
                  objectKind: 'entity',
                  routeId: 'homepageDetail',
                ),
              ),
            ],
    );
  }

  testWidgets('无可用交集时 fromReasons 返回 null（不占位）', (tester) async {
    expect(
      ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: const <IntersectionReason>[],
        isDark: false,
      ),
      isNull,
    );
    expect(
      ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: <IntersectionReason>[
          reason(dimension: 'interest', tagRefs: const [], primaryText: '   '),
        ],
        isDark: false,
      ),
      isNull,
    );
  });

  testWidgets('onReasonTap 回调携带 dimension/tagRefs（交集归因输入）', (tester) async {
    IntersectionReason? tapped;
    final card = ObjectIntersectionCard.fromReasons(
      title: '你们的交集',
      reasons: <IntersectionReason>[
        reason(
          dimension: 'interest',
          tagRefs: const <String>['Topic/摄影', 'Topic/旅行'],
          primaryText: '你们都喜欢 摄影',
        ),
      ],
      isDark: false,
      onReasonTap: (r) => tapped = r,
    );
    expect(card, isNotNull);

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: card!)));
    await tester.pump();

    expect(find.text('你们都喜欢 摄影'), findsOneWidget);

    await tester.tap(find.byType(IntersectionStatementRow));
    await tester.pump();

    expect(tapped, isNotNull);
    expect(tapped!.dimension, 'interest');
    expect(tapped!.tagRefs, <String>['Topic/摄影', 'Topic/旅行']);
  });
}
