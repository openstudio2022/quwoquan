import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/micro_post_dto.g.dart';
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

    expect(find.text('都在看川西攻略'), findsOneWidget);
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

  testWidgets('交集 spotlight 只展示可行动对象理由（统一原子：名字+维度chip）', (tester) async {
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
              relationKind: 'circle',
              displayName: '摄影圈',
              actionType: 'join_circle',
              actionTargetId: 'circle_photo',
              sharedCount: 6,
            ),
          ],
          onReasonTap: (_) => opened = true,
        ),
      ),
    );

    // 统一原子展示 displayName（名字）而非端拼整句；无目标理由不渲染。
    expect(find.text('摄影圈'), findsOneWidget);
    expect(find.text('仅解释无目标'), findsNothing);
    await tester.tap(find.byKey(const ValueKey<String>('spotlight-object-0')));
    expect(opened, isTrue);
  });
}
