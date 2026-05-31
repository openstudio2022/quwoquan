import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';

/// 统计行（圈子/关注/粉丝）三栏：值取自 profile，点击经 onStatTap 分发对应 type。
SubAccountProfileViewData _profile() {
  return const SubAccountProfileViewData(
    subAccountId: 'sa1',
    ownerUserId: 'u1',
    subjectType: 'user',
    userHandle: 'nature',
    username: 'nature',
    displayName: '自然摄影师',
    avatarUrl: '',
    backgroundUrl: '',
    bio: '',
    followerCount: 30,
    followingCount: 12,
    postCount: 5,
    circleCount: 8,
    likeCount: 0,
    isolationLevel: 'standard',
    profileVisibility: 'public',
    inheritsFromOwner: false,
    overriddenFields: <String>[],
    updatedAt: null,
  );
}

void main() {
  testWidgets('渲染三栏统计值与同源标签', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProfileStatsRow(isDark: false, profile: _profile()),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('8'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('30'), findsOneWidget);
    expect(find.text(UITextConstants.contactsTabCircles), findsOneWidget);
    expect(find.text(UITextConstants.follow), findsOneWidget);
    expect(find.text(UITextConstants.circleFans), findsOneWidget);
  });

  testWidgets('点击统计栏分发对应 type', (tester) async {
    final tapped = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProfileStatsRow(
            isDark: false,
            profile: _profile(),
            onStatTap: tapped.add,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.text(UITextConstants.contactsTabCircles));
    await tester.tap(find.text(UITextConstants.follow));
    await tester.tap(find.text(UITextConstants.circleFans));
    await tester.pump();

    expect(tapped, <String>['circles', 'following', 'fans']);
  });
}
