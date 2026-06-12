import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';

/// 统计行四列（关注/粉丝/获赞/作品）：值取自 profile；
/// 关注/粉丝点击经 onStatTap 分发对应 type，获赞/作品为静态格不可点。
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
    likeCount: 256,
    isolationLevel: 'standard',
    profileVisibility: 'public',
    inheritsFromOwner: false,
    overriddenFields: <String>[],
    updatedAt: null,
  );
}

void main() {
  testWidgets('渲染四列统计值与同源标签', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProfileStatsRow(isDark: false, profile: _profile()),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('12'), findsOneWidget);
    expect(find.text('30'), findsOneWidget);
    expect(find.text('256'), findsOneWidget);
    expect(find.text('5'), findsOneWidget);
    expect(find.text(UITextConstants.follow), findsOneWidget);
    expect(find.text(UITextConstants.circleFans), findsOneWidget);
    expect(find.text(UITextConstants.circleLikes), findsOneWidget);
    expect(find.text(UITextConstants.discoveryRailWorks), findsOneWidget);
  });

  testWidgets('点击统计栏分发对应 type；获赞/作品为静态格不分发', (tester) async {
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

    await tester.tap(find.text(UITextConstants.follow));
    await tester.tap(find.text(UITextConstants.circleFans));
    await tester.tap(
      find.text(UITextConstants.circleLikes),
      warnIfMissed: false,
    );
    await tester.tap(
      find.text(UITextConstants.discoveryRailWorks),
      warnIfMissed: false,
    );
    await tester.pump();

    expect(tapped, <String>['following', 'fans']);
  });
}
