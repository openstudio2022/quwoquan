import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/micro_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/discovery/widgets/dual_column_discovery_post_card.dart';
import 'package:quwoquan_app/ui/discovery/widgets/intersection_spotlight_module.dart';

MicroPostDto _post() {
  return MicroPostDto(
    id: 'post_intersection_demo',
    type: 'moment',
    identity: 'moment',
    authorId: 'user_demo',
    displayName: '小趣用户',
    avatarUrl: '',
    assistantUsePolicy: 'allow',
    likeCount: 12,
    commentCount: 3,
    favoriteCount: 2,
    shareCount: 1,
    createdAt: DateTime(2026),
    body: '川西雪山和校园摄影路线',
    imageUrls: const <String>[''],
    intersectionReasons: <IntersectionReason>[
      IntersectionReason(
        dimension: 'interest',
        tagRefs: <String>['Topic/旅行'],
        relationKind: 'place',
        displayText: '都在看川西攻略',
        actionType: 'follow',
        actionTargetId: 'entity_chuanxi',
        sharedCount: 8,
        intersectionPoints: <IntersectionPoint>[
          IntersectionPoint(
            pointId: 'post_ix_1',
            pointClass: 'fact',
            dimension: 'interest',
            displayText: '都在看川西攻略',
          ),
        ],
        factPointCount: 1,
        totalPointCount: 1,
      ),
    ],
  );
}

void main() {
  testWidgets('双列发现卡展示短交集理由并响应点击', (tester) async {
    var tapped = false;
    var liked = false;
    await tester.binding.setSurfaceSize(const Size(390, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: SizedBox(
            width: 180,
            child: DualColumnDiscoveryPostCard(
              item: _post(),
              isDark: false,
              isLiked: false,
              likeCount: 12,
              onTap: () => tapped = true,
              onUserTap: () {},
              onLikeTap: () => liked = true,
            ),
          ),
        ),
      ),
    );

    // 新口径：最强证据组短句（count 为 0 时仅短句，零内部词）。
    expect(find.text('都在看川西攻略'), findsOneWidget);
    expect(find.textContaining('个交集点'), findsNothing);
    expect(find.text('川西雪山和校园摄影路线'), findsOneWidget);
    await tester.tap(find.byType(DualColumnDiscoveryPostCard));
    expect(tapped, isTrue);
    await tester.tap(find.byIcon(CupertinoIcons.heart));
    expect(liked, isTrue);
  });

  testWidgets('双列发现卡在窄宽度下不发生右侧溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    FlutterErrorDetails? overflow;
    final oldOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('A RenderFlex overflowed')) {
        overflow = details;
      }
      oldOnError?.call(details);
    };
    addTearDown(() => FlutterError.onError = oldOnError);

    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: SizedBox(
            width: 132,
            child: DualColumnDiscoveryPostCard(
              item: _post(),
              isDark: false,
              isLiked: false,
              likeCount: 12345,
              onTap: () {},
              onUserTap: () {},
              onLikeTap: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(overflow, isNull);
  });

  testWidgets('交集 spotlight 只展示可行动对象（等高关系封面卡：名字+最强证据组）', (
    tester,
  ) async {
    var opened = false;
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      CupertinoApp(
        home: IntersectionSpotlightModule(
          isDark: false,
          reasons: <IntersectionReason>[
            // 无 actionTargetId：不可行动，应被过滤。
            IntersectionReason(displayName: '仅解释无目标'),
            IntersectionReason(
              dimension: 'interest',
              intersectionClass: 'affinity',
              relationKind: 'circle',
              displayName: '摄影圈',
              displayText: '共同关注摄影内容',
              confidenceLabel: '推荐',
              actionType: 'join_circle',
              actionTargetId: 'circle_photo',
              sharedCount: 0,
              intersectionPoints: <IntersectionPoint>[
                IntersectionPoint(
                  pointId: 'ix_photo_point',
                  pointClass: 'recommended',
                  dimension: 'interest',
                  label: '摄影内容相似',
                  displayText: '共同关注摄影内容',
                ),
              ],
              recommendedPointCount: 1,
              totalPointCount: 1,
              pointClassLabel: '推荐交集',
            ),
          ],
          onReasonTap: (_) => opened = true,
        ),
      ),
    );

    // 等高封面卡：对象名 + 最强证据组短句；概率推荐显示「推荐」角标；
    // 零内部词、零空数字（count=0 不显示「0」）。
    expect(find.text('摄影圈'), findsOneWidget);
    expect(find.text('共同关注摄影内容'), findsOneWidget);
    expect(find.text('推荐'), findsWidgets);
    expect(find.textContaining('个推荐交集点'), findsNothing);
    expect(find.text('0 共同点'), findsNothing);
    expect(find.text('仅解释无目标'), findsNothing);
    await tester.tap(find.text('摄影圈'), warnIfMissed: false);
    await tester.pump();
    expect(opened, isTrue);
  });

  testWidgets('交集 spotlight 在窄宽度下不发生底部 overflow', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    FlutterErrorDetails? overflow;
    final oldOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('A RenderFlex overflowed')) {
        overflow = details;
      }
      oldOnError?.call(details);
    };
    addTearDown(() => FlutterError.onError = oldOnError);

    await tester.pumpWidget(
      CupertinoApp(
        home: SizedBox(
          width: 320,
          child: IntersectionSpotlightModule(
            isDark: false,
            reasons: <IntersectionReason>[
              IntersectionReason(
                dimension: 'relationship',
                relationKind: 'circle',
                displayName: '摄影圈摄影圈摄影圈',
                displayText: '共同关注摄影内容',
                actionType: 'join_circle',
                actionTargetId: 'circle_photo',
                intersectionId: 'ix_circle_photo',
                intersectionPoints: <IntersectionPoint>[
                  IntersectionPoint(
                    pointId: 'ix_photo_point_fact',
                    pointClass: 'fact',
                    dimension: 'relationship',
                    label: '共同关注特别多并且最近一起活跃',
                    displayText: '共同关注特别多并且最近一起活跃',
                    count: 12,
                    sampleText: '老同学 李航和周屿都在这里',
                  ),
                ],
                factPointCount: 1,
                totalPointCount: 1,
              ),
            ],
            onReasonTap: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(overflow, isNull);
  });

  testWidgets('交集 spotlight「换一批」：候选窗内轮转出下一批对象', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    IntersectionReason cover(String id, String name) => IntersectionReason(
      dimension: 'relationship',
      relationKind: 'person',
      displayName: name,
      actionType: 'view_object',
      actionTargetId: id,
      intersectionId: 'ix_$id',
      intersectionPoints: <IntersectionPoint>[
        IntersectionPoint(
          pointId: '${id}_p',
          pointClass: 'fact',
          dimension: 'relationship',
          label: '共同关注',
          displayText: '共同关注',
          count: 3,
        ),
      ],
    );

    await tester.pumpWidget(
      CupertinoApp(
        home: IntersectionSpotlightModule(
          isDark: false,
          windowSize: 2,
          reasons: <IntersectionReason>[
            cover('a', '阿一'),
            cover('b', '阿二'),
            cover('c', '阿三'),
            cover('d', '阿四'),
          ],
          onReasonTap: (_) {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 第一屏：前 2 个对象（windowSize=2）。
    expect(find.text('阿一'), findsOneWidget);
    expect(find.text('阿二'), findsOneWidget);

    // 候选窗 > windowSize → 出现「换一批」。
    final shuffle = find.byKey(IntersectionSpotlightModule.shuffleKey);
    expect(shuffle, findsOneWidget);

    await tester.tap(shuffle);
    await tester.pumpAndSettle();

    // 换一批后轮转到下一批（看过的保留在候选窗，只是被顶替展示）。
    expect(find.text('阿三'), findsOneWidget);
    expect(find.text('阿四'), findsOneWidget);
  });
}
