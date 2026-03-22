import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

Widget _wrap(Widget child) {
  return MaterialApp(
    home: Scaffold(body: SizedBox(width: 390, child: child)),
  );
}

void main() {
  testWidgets('右侧三按钮组内间距接近一致且整体右锚定', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '你的皮',
          circleName: '',
          likeCount: 234,
          shareCount: 4,
          commentCount: 36,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();

    final heart = tester.getCenter(find.byIcon(CupertinoIcons.heart));
    final share = tester.getCenter(
      find.byIcon(CupertinoIcons.arrowshape_turn_up_right),
    );
    final comment = tester.getCenter(find.byIcon(CupertinoIcons.chat_bubble));
    final actionGroupRect = tester.getRect(
      find.byKey(const ValueKey('immersive-actions-group')),
    );
    final rootRect = tester.getRect(find.byType(ImmersiveEngagementBar));

    final likeToShare = share.dx - heart.dx;
    final shareToComment = comment.dx - share.dx;
    final rightMargin = rootRect.right - actionGroupRect.right;

    expect((likeToShare - shareToComment).abs(), lessThan(4));
    expect((rightMargin - AppSpacing.containerMd).abs(), lessThan(1));
  });

  testWidgets('我的 post 使用无作者栏的一行三等分工具栏', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '我的名字',
          circleName: '',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: true,
          isFollowing: false,
          isSelfPost: true,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('immersive-self-actions-group')),
      findsOneWidget,
    );
    expect(find.byType(CircleAvatar), findsNothing);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('8'), findsOneWidget);
    expect(find.text('5'), findsOneWidget);

    final selfGroupRect = tester.getRect(
      find.byKey(const ValueKey('immersive-self-actions-group')),
    );
    final rootRect = tester.getRect(find.byType(ImmersiveEngagementBar));
    expect((selfGroupRect.center.dy - rootRect.center.dy).abs(), lessThan(4));
  });
}

void _noop() {}
