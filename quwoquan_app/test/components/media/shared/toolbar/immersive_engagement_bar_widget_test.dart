import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

Widget _wrap(Widget child, {double width = 390}) {
  return MaterialApp(
    home: Scaffold(
      body: MediaQuery(
        data: MediaQueryData(size: Size(width, 800)),
        child: SizedBox(width: width, child: child),
      ),
    ),
  );
}

double _expectedNameSlotWidth(int visibleChars) {
  final displayStyle = TextStyle(
    fontSize: AppTypography.sm,
    fontWeight: AppTypography.medium,
  );
  final secondaryStyle = TextStyle(
    fontSize: AppTypography.xxs,
    fontWeight: AppTypography.medium,
  );
  final displayWidth = _measureTextWidth(
    visibleChars,
    displayStyle,
    includeEllipsis: true,
  );
  final secondaryWidth = _measureTextWidth(
    visibleChars,
    secondaryStyle,
    includeEllipsis: true,
  );
  return displayWidth > secondaryWidth ? displayWidth : secondaryWidth;
}

double _measureTextWidth(
  int charCount,
  TextStyle style, {
  bool includeEllipsis = false,
}) {
  const sample = '一二三四五六七八九十';
  final text = sample.substring(0, charCount);
  final painter = TextPainter(
    text: TextSpan(
      text: '$text${includeEllipsis ? '...' : ''}',
      style: style,
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  return painter.width;
}

void main() {
  testWidgets('右侧三按钮组内间距一致且动作组整体右锚定到 track', (tester) async {
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
    final railRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );
    final rootRect = tester.getRect(find.byType(ImmersiveEngagementBar));

    final likeToShare = share.dx - heart.dx;
    final shareToComment = comment.dx - share.dx;

    expect((likeToShare - shareToComment).abs(), lessThan(4));
    // 动作组右缘完全贴合 track 右缘（固定宽 + 右锚定）
    expect((railRect.right - actionGroupRect.right).abs(), lessThan(1));
    // Track 外侧留白 = 水平 inset
    expect((rootRect.right - railRect.right - AppSpacing.containerMd).abs(), lessThan(1));
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

  testWidgets('iPad 宽屏下作者左锚 rail 左缘、动作右锚 rail 右缘（与顶部/内容共享 rail）', (
    tester,
  ) async {
    const width = 1024.0;
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
          avatarUrl: '',
          displayName: 'TechDaily',
          circleName: '',
          likeCount: 1200,
          shareCount: 89,
          commentCount: 56,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: width,
      ),
    );
    await tester.pumpAndSettle();

    final rootRect = tester.getRect(find.byType(ImmersiveEngagementBar));
    final railRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );
    final authorRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-group')),
    );
    final actionRect = tester.getRect(
      find.byKey(const ValueKey('immersive-actions-group')),
    );

    // mediaStage 无内容宽上限，rail 填满 containerMd inset 之后的全部可用宽度
    expect((railRect.left - AppSpacing.containerMd).abs(), lessThan(1));
    expect(
      (rootRect.right - railRect.right - AppSpacing.containerMd).abs(),
      lessThan(1),
    );
    // 作者左缘锚 rail 左缘，动作右缘锚 rail 右缘
    expect((authorRect.left - railRect.left).abs(), lessThan(1));
    expect((railRect.right - actionRect.right).abs(), lessThan(1));
  });

  testWidgets('iPad 宽屏下 clusterGap 等于档位常量 interGroupLg，中间余量落在 RightSpacer', (
    tester,
  ) async {
    const width = 1024.0;
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证宽屏下不会把空白全部留给两组之间',
          circleName: '',
          likeCount: 8200,
          shareCount: 560,
          commentCount: 430,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: width,
      ),
    );
    await tester.pumpAndSettle();

    final authorRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-group')),
    );
    final actionRect = tester.getRect(
      find.byKey(const ValueKey('immersive-actions-group')),
    );
    final railRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );

    // 作者组 -> 关注槽位 -> clusterGap(=interGroupLg 档位常量) -> RightSpacer -> 动作组
    // 组间距本身就是 interGroupLg，RightSpacer 吸收剩余，不会影响 clusterGap 数值；
    // 整段"作者右缘到动作左缘"至少包含 clusterGap。
    final betweenGroups = actionRect.left - authorRect.right;
    expect(
      betweenGroups,
      greaterThanOrEqualTo(AppSpacing.interGroupLg - 1),
    );

    // 动作右缘严格贴合 rail 右缘，作者左缘严格贴合 rail 左缘
    expect((railRect.right - actionRect.right).abs(), lessThan(1));
    expect((authorRect.left - railRect.left).abs(), lessThan(1));
  });

  testWidgets('follow 按钮显隐不影响 track 位置与动作组位置（同档位稳定）', (tester) async {
    Future<Rect> pumpAndGetActionRect({required bool showFollow}) async {
      await tester.pumpWidget(
        _wrap(
          ImmersiveEngagementBar(
            avatarUrl: '',
            displayName: '稳定用户',
            circleName: '',
            likeCount: 12,
            shareCount: 8,
            commentCount: 5,
            isLiked: false,
            isFollowing: false,
            showFollowButton: showFollow,
            onUserTap: _noop,
            onCircleTap: _noop,
            onFollowTap: _noop,
            onLikeTap: _noop,
          ),
          width: 390,
        ),
      );
      await tester.pumpAndSettle();
      return tester.getRect(
        find.byKey(const ValueKey('immersive-actions-group')),
      );
    }

    final withoutFollow = await pumpAndGetActionRect(showFollow: false);
    final withFollow = await pumpAndGetActionRect(showFollow: true);

    // 动作组的左缘完全稳定（槽位始终保留，show/hide 只改变可见性）
    expect(
      (withoutFollow.left - withFollow.left).abs(),
      lessThan(1),
      reason: 'follow 显隐不应改变赞按钮位置',
    );
    expect(
      (withoutFollow.right - withFollow.right).abs(),
      lessThan(1),
    );
  });

  testWidgets('手机窄屏固定显示 4 个作者名宽度', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证固定宽度',
          circleName: '',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 320,
      ),
    );
    await tester.pumpAndSettle();

    final nameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    // 允许降级链压缩少量像素以防止溢出
    expect(nameRect.width, lessThanOrEqualTo(_expectedNameSlotWidth(4) + 1));
  });

  testWidgets('常规手机固定显示 5 个作者名宽度且 follow 开关不漂移', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证固定宽度',
          circleName: '',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          showFollowButton: false,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 390,
      ),
    );
    await tester.pumpAndSettle();
    final hiddenFollowNameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );

    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证固定宽度',
          circleName: '',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          showFollowButton: true,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 390,
      ),
    );
    await tester.pumpAndSettle();
    final shownFollowNameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    final followRect = tester.getRect(
      find.byKey(const ValueKey('immersive-follow-button')),
    );

    // 作者名槽位宽度不因 follow 显隐而改变
    expect(
      (hiddenFollowNameRect.width - shownFollowNameRect.width).abs(),
      lessThan(1),
    );
    // 作者名宽度不超过档位上限
    expect(
      shownFollowNameRect.width,
      lessThanOrEqualTo(_expectedNameSlotWidth(5) + 1),
    );
    // follow 按钮紧贴作者名右缘 + intraGroupXs
    expect(
      (followRect.left - shownFollowNameRect.right - AppSpacing.intraGroupXs)
          .abs(),
      lessThan(2),
    );
  });

  testWidgets('大手机及以上固定显示 6 个作者名宽度', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证固定宽度',
          circleName: '',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onCircleTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 430,
      ),
    );
    await tester.pumpAndSettle();

    final nameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    expect(
      nameRect.width,
      lessThanOrEqualTo(_expectedNameSlotWidth(6) + 1),
    );
  });
}

void _noop() {}
