import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';

/// 统计行单行四项（粉丝/关注/获赞/圈子）：值取自 profile；
/// 四项点击经 onStatTap 分发对应 type。
PersonaProfileViewData _profile() {
  return const PersonaProfileViewData(
    personaId: 'sa1',
    ownerUserId: 'u1',
    subjectType: 'user',
    userHandle: 'nature',
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
  testWidgets('渲染单行四项统计值与同源标签，不展示记录数', (tester) async {
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
    expect(find.text('8'), findsOneWidget);
    expect(find.text('5'), findsNothing);
    expect(find.text(ProfileText.profileStatRecords), findsNothing);
    expect(find.text(ProfileText.profileStatFollowers), findsOneWidget);
    expect(find.text(FoundationText.follow), findsOneWidget);
    expect(find.text(CommunityText.circleLikes), findsOneWidget);
    expect(find.text(ChatText.contactsTabCircles), findsOneWidget);
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

    await tester.tap(find.text(ProfileText.profileStatFollowers));
    await tester.tap(find.text(FoundationText.follow));
    await tester.tap(find.text(CommunityText.circleLikes));
    await tester.tap(find.text(ChatText.contactsTabCircles));
    await tester.pump();

    expect(tapped, <String>['fans', 'following', 'likes', 'circles']);
  });
}
