// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018.t1
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

Widget _wrap(Widget child, {double width = 390, double bottomInset = 0}) {
  return MaterialApp(
    home: Scaffold(
      body: MediaQuery(
        data: MediaQueryData(
          size: Size(width, 800),
          padding: EdgeInsets.only(bottom: bottomInset),
          viewPadding: EdgeInsets.only(bottom: bottomInset),
        ),
        child: SizedBox(width: width, child: child),
      ),
    ),
  );
}

double _nameSlotWidthForChars(int charCount) {
  const sample = '一二三四五六七八九十';
  final tp = TextPainter(
    text: TextSpan(
      text: sample.substring(0, charCount),
      style: const TextStyle(
        fontSize: AppTypography.sm,
        fontWeight: AppTypography.medium,
      ),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  return tp.width;
}

void main() {
  testWidgets('右侧三按钮组内间距一致且动作组整体右锚定到 track', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '你的皮',
          likeCount: 234,
          shareCount: 4,
          commentCount: 36,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();

    final heart = tester.getCenter(find.byType(AppMediaHeartIcon));
    final share = tester.getCenter(find.byType(AppMediaShareIcon));
    final comment = tester.getCenter(find.byType(AppMediaCommentIcon));
    final actionGroupRect = tester.getRect(
      find.byKey(const ValueKey('immersive-actions-group')),
    );
    final railRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );
    final rootRect = tester.getRect(find.byType(ImmersiveEngagementBar));

    final likeToShare = share.dx - heart.dx;
    final shareToComment = comment.dx - share.dx;

    expect((likeToShare - shareToComment).abs(), lessThan(6));
    // 动作组右缘完全贴合 track 右缘（固定宽 + 右锚定）
    expect((railRect.right - actionGroupRect.right).abs(), lessThan(1));
    // Track 外侧留白 = 水平 inset
    expect(
      (rootRect.right - railRect.right - AppSpacing.containerMd).abs(),
      lessThan(1),
    );
  });

  testWidgets('作者认证角标随云侧快照显示，空字段不渲染', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '认证作者',
          authorBadge: 'verified_creator',
          likeCount: 1,
          shareCount: 1,
          commentCount: 1,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('immersive-author-badge')),
      findsOneWidget,
    );

    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '普通作者',
          likeCount: 1,
          shareCount: 1,
          commentCount: 1,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('immersive-author-badge')), findsNothing);
  });

  testWidgets('我的 post 使用无作者栏的一行三等分工具栏', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '我的名字',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: true,
          isFollowing: false,
          isSelfPost: true,
          onUserTap: _noop,
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
          likeCount: 1200,
          shareCount: 89,
          commentCount: 56,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
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

    // mediaStage：全宽 rail，仅 containerMd 水平 inset，不收窄到 feedMaxContentWidth。
    expect((railRect.left - AppSpacing.containerMd).abs(), lessThan(1));
    expect(
      (rootRect.right - railRect.right - AppSpacing.containerMd).abs(),
      lessThan(1),
    );
    expect(
      (railRect.width - (rootRect.width - AppSpacing.containerMd * 2)).abs(),
      lessThan(1),
    );
    // 作者左缘锚 rail 左缘，动作右缘锚 rail 右缘
    expect((authorRect.left - railRect.left).abs(), lessThan(1));
    expect((railRect.right - actionRect.right).abs(), lessThan(1));
  });

  testWidgets('iPad 宽屏下 clusterGap 保持组间距语义', (tester) async {
    const width = 1024.0;
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证宽屏下不会把空白全部留给两组之间',
          likeCount: 8200,
          shareCount: 560,
          commentCount: 430,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
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

    // 作者组 -> 关注槽位 -> clusterGap(=interGroupMd 档位常量) -> RightSpacer -> 动作组
    // 组间距本身就是 interGroupMd，RightSpacer 吸收剩余，不会影响 clusterGap 数值；
    // 整段"作者右缘到动作左缘"至少包含 clusterGap。
    final betweenGroups = actionRect.left - authorRect.right;
    expect(betweenGroups, greaterThanOrEqualTo(AppSpacing.interGroupMd - 1));

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
            likeCount: 12,
            shareCount: 8,
            commentCount: 5,
            isLiked: false,
            isFollowing: false,
            showFollowButton: showFollow,
            onUserTap: _noop,
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
    expect((withoutFollow.right - withFollow.right).abs(), lessThan(1));
  });

  testWidgets('手机窄屏 12 字作者名两行展示且不越过关注槽位左缘', (tester) async {
    const twelveChars = '一二三四五六七八九十甲乙';
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: twelveChars,
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 320,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(twelveChars), findsOneWidget);
    final textRect = tester.getRect(find.text(twelveChars));
    expect(textRect.height, greaterThan(18));
    final nameSlotRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    final followLaneRect = tester.getRect(
      find.byKey(const ValueKey('immersive-follow-lane')),
    );
    expect(nameSlotRect.right, lessThanOrEqualTo(followLaneRect.left + 1));
  });

  testWidgets('常规手机 follow 出现时作者名保持 5 字固定槽且动作组不变', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '特别长的作者名字用于验证固定宽度',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          showFollowButton: false,
          onUserTap: _noop,
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
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          showFollowButton: true,
          onUserTap: _noop,
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

    // regular 档位固定 5 字槽，follow 出现不按文本长度移动槽位。
    expect(
      (hiddenFollowNameRect.width - shownFollowNameRect.width).abs(),
      lessThan(1),
    );
    expect(
      shownFollowNameRect.width,
      moreOrLessEquals(_nameSlotWidthForChars(5), epsilon: 1),
    );
    // follow 按钮紧贴作者名右缘 + intraGroupXs
    expect(
      (followRect.left - shownFollowNameRect.right - AppSpacing.intraGroupXs)
          .abs(),
      lessThan(2),
    );
  });

  testWidgets('iPad 三字作者名仍占 6 字固定槽位', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
          avatarUrl: '',
          displayName: '纸上居',
          likeCount: 117,
          shareCount: 6,
          commentCount: 0,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 1024,
      ),
    );
    await tester.pumpAndSettle();

    final nameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    final followRect = tester.getRect(
      find.byKey(const ValueKey('immersive-follow-button')),
    );

    expect(
      nameRect.width,
      moreOrLessEquals(_nameSlotWidthForChars(6), epsilon: 1),
    );
    expect(
      (followRect.left - nameRect.right - AppSpacing.intraGroupXs).abs(),
      lessThan(2),
    );
  });

  testWidgets('iPad 五字作者名在 6 字槽内单行完整展示', (tester) async {
    const authorName = '城市观察员';
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
          avatarUrl: '',
          displayName: authorName,
          likeCount: 211,
          shareCount: 18,
          commentCount: 0,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 1024,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(authorName), findsOneWidget);
    final nameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    final textRect = tester.getRect(find.text(authorName));

    expect(
      nameRect.width,
      moreOrLessEquals(_nameSlotWidthForChars(6), epsilon: 1),
    );
    expect(textRect.height, lessThan(22));
  });

  testWidgets('作者名超过 12 字截断为 12 字展示', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '一二三四五六七八九十甲乙丙丁戊',
          likeCount: 1,
          shareCount: 1,
          commentCount: 1,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 390,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('一二三四五六七八九十甲乙'), findsOneWidget);
    expect(find.textContaining('丙'), findsNothing);
  });

  testWidgets('单字作者名单行展示', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '甲',
          likeCount: 1,
          shareCount: 1,
          commentCount: 1,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 390,
      ),
    );
    await tester.pumpAndSettle();

    final textRect = tester.getRect(find.text('甲'));
    expect(textRect.height, lessThan(22));
  });

  testWidgets('iPad 宽屏 12 字作者名使用 6 字槽并启用两行兜底', (tester) async {
    const twelveChars = '一二三四五六七八九十甲乙';
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
          avatarUrl: '',
          displayName: twelveChars,
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 1024,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(twelveChars), findsOneWidget);
    final nameRect = tester.getRect(
      find.byKey(const ValueKey('immersive-author-name-slot')),
    );
    final textWidget = tester.widget<Text>(find.text(twelveChars));

    expect(
      nameRect.width,
      moreOrLessEquals(_nameSlotWidthForChars(6), epsilon: 1),
    );
    expect(textWidget.maxLines, 2);
  });

  testWidgets('圆弧机型底部安全区只垂直抬升，rail 左右保持统一对齐轨道', (tester) async {
    const bottomInset = 34.0;
    const viewports = <double>[320, 390, 768];

    for (final width in viewports) {
      await tester.pumpWidget(
        _wrap(
          const ImmersiveEngagementBar(
            layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
            avatarUrl: '',
            displayName: '自然摄影师',
            likeCount: 1200,
            shareCount: 18,
            commentCount: 45,
            isLiked: false,
            isFollowing: false,
            onUserTap: _noop,
            onFollowTap: _noop,
            onLikeTap: _noop,
          ),
          width: width,
          bottomInset: bottomInset,
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
      // 对齐轨道单源（REQ-019）：底部安全区不再叠加侧向收窄，
      // rail 左右 inset 与顶栏/caption 完全一致。
      final expectedHorizontalInset = AppSpacing.containerMd;

      expect(
        railRect.left,
        moreOrLessEquals(expectedHorizontalInset, epsilon: 1),
        reason: 'width=$width: rail 左缘必须落在统一对齐轨道上',
      );
      expect(
        rootRect.right - railRect.right,
        moreOrLessEquals(expectedHorizontalInset, epsilon: 1),
        reason: 'width=$width: rail 右缘必须落在统一对齐轨道上',
      );
      expect(
        railRect.right - actionRect.right,
        lessThan(1),
        reason: 'width=$width: 动作组仍应右锚到 rail',
      );
      expect(
        authorRect.right,
        lessThanOrEqualTo(actionRect.left),
        reason: 'width=$width: 作者/关注槽位不能挤压动作组',
      );
      // 垂直保护（REQ-019）：内容区在 home indicator 之上再抬升 lift。
      expect(
        rootRect.bottom - railRect.bottom,
        moreOrLessEquals(
          bottomInset + AppSpacing.immersiveBottomChromeLift,
          epsilon: 1,
        ),
        reason: 'width=$width: 底部安全区保护必须以垂直抬升表达',
      );
    }
  });

  testWidgets('底栏只承载作者与互动动作，不再渲染内容区交集句', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: 'Alpha 长',
          likeCount: 720,
          shareCount: 16,
          commentCount: 0,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('immersive-intersection-statement')),
      findsNothing,
    );
    expect(find.textContaining('个交集'), findsNothing);
  });

  testWidgets('单行作者名不使用透明渐隐遮罩避免局部阴影', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: 'Alpha 长',
          likeCount: 720,
          shareCount: 16,
          commentCount: 0,
          isLiked: false,
          isFollowing: false,
          showFollowButton: true,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
        width: 390,
      ),
    );
    await tester.pumpAndSettle();

    final authorName = find.text('Alpha 长');
    expect(authorName, findsOneWidget);
    expect(
      find.ancestor(of: authorName, matching: find.byType(ShaderMask)),
      findsNothing,
    );
    final textWidget = tester.widget<Text>(authorName);
    expect(textWidget.overflow, isNot(TextOverflow.fade));
  });

  testWidgets('无头像时底栏头像仍显示兜底人像图标', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ImmersiveEngagementBar(
          avatarUrl: '',
          displayName: '头像用户',
          likeCount: 12,
          shareCount: 8,
          commentCount: 5,
          isLiked: false,
          isFollowing: false,
          onUserTap: _noop,
          onFollowTap: _noop,
          onLikeTap: _noop,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(RoundedSquareAvatar), findsOneWidget);
    expect(find.byIcon(Icons.person), findsOneWidget);
  });
}

void _noop() {}
