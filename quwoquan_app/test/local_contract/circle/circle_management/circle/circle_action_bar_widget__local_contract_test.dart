import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/circle/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_app/circle/circle_management/circle/presentation/circle_action_bar.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CircleJoinPolicy;

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('CircleActionBar - 首屏 CTA 契约', () {
    testWidgets('owner 首屏不展示管理入口，只展示已加入与进入讨论', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.owner,
            joinStatus: 'joined',
          ),
        ),
      );

      expect(find.text(CommunityText.joinedCircle), findsOneWidget);
      expect(
        find.text(ObjectHomepageText.circleActionEnterDiscussion),
        findsOneWidget,
      );
      expect(find.text(CommunityText.editCircle), findsNothing);
      expect(find.text(CommunityText.manageCenter), findsNothing);
    });

    testWidgets('visitor 默认显示加入和进入讨论', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
          ),
        ),
      );

      expect(find.text(CommunityText.joinCircle), findsOneWidget);
      expect(
        find.text(ObjectHomepageText.circleActionEnterDiscussion),
        findsOneWidget,
      );
      expect(find.text(CommunityText.followCircle), findsNothing);
    });

    testWidgets('审批圈子 visitor 显示申请加入和进入讨论', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            joinPolicy: CircleJoinPolicy.approval,
          ),
        ),
      );

      expect(find.text(CommunityText.circleJoinApproval), findsOneWidget);
      expect(
        find.text(ObjectHomepageText.circleActionEnterDiscussion),
        findsOneWidget,
      );
    });

    testWidgets('待审核态显示加入审批中和进入讨论', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: true,
            role: CircleRole.visitor,
            joinStatus: 'pending',
          ),
        ),
      );

      expect(find.text(CommunityText.joinPending), findsOneWidget);
      expect(
        find.text(ObjectHomepageText.circleActionEnterDiscussion),
        findsOneWidget,
      );
    });

    testWidgets('仅邀请圈子展示不可主动触发的加入动作', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            joinPolicy: CircleJoinPolicy.inviteOnly,
            onJoinCircle: () => called = true,
          ),
        ),
      );

      expect(find.text(CommunityText.circleJoinInviteOnly), findsOneWidget);
      await tester.tap(find.text(CommunityText.circleJoinInviteOnly));
      await tester.pump();
      expect(called, isFalse);
    });
  });

  group('CircleActionBar - 交互契约', () {
    testWidgets('visitor 点击加入圈子触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            onJoinCircle: () => called = true,
          ),
        ),
      );

      await tester.tap(find.text(CommunityText.joinCircle));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('点击进入讨论触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.member,
            joinStatus: 'joined',
            onEnterDiscussion: () => called = true,
          ),
        ),
      );

      await tester.tap(
        find.text(ObjectHomepageText.circleActionEnterDiscussion),
      );
      await tester.pump();

      expect(called, isTrue);
    });
  });
}
