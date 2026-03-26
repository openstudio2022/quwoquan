import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';

Widget _wrap(Widget child) => MaterialApp(
  home: Scaffold(body: child),
);

void main() {
  group('CircleActionBar - 渲染契约', () {
    testWidgets('owner 显示编辑圈子与管理中心', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.owner,
            joinStatus: 'joined',
          ),
        ),
      );

      expect(find.text(UITextConstants.editCircle), findsOneWidget);
      expect(find.text(UITextConstants.manageCenter), findsOneWidget);
    });

    testWidgets('admin 显示编辑圈子与管理中心', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.admin,
            joinStatus: 'joined',
          ),
        ),
      );

      expect(find.text(UITextConstants.editCircle), findsOneWidget);
      expect(find.text(UITextConstants.manageCenter), findsOneWidget);
    });

    testWidgets('member 显示圈聊与已加入圈子', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.member,
            joinStatus: 'joined',
            hasConversation: true,
          ),
        ),
      );

      expect(find.text(UITextConstants.circleGroups), findsOneWidget);
      expect(find.text(UITextConstants.joinedCircle), findsOneWidget);
    });

    testWidgets('visitor 默认显示加入圈子与关注圈子', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            isFollowed: false,
          ),
        ),
      );

      expect(find.text(UITextConstants.joinCircle), findsOneWidget);
      expect(find.text(UITextConstants.followCircle), findsOneWidget);
    });

    testWidgets('审批圈子 visitor 显示申请加入与关注圈子', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            joinPolicy: 'approval',
            isFollowed: false,
          ),
        ),
      );

      expect(find.text(UITextConstants.circleJoinApproval), findsOneWidget);
      expect(find.text(UITextConstants.followCircle), findsOneWidget);
    });

    testWidgets('粉丝态显示已关注圈子', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            isFollowed: true,
          ),
        ),
      );

      expect(find.text(UITextConstants.followedCircle), findsOneWidget);
    });

    testWidgets('待审核态显示加入审批中与已关注圈子', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'pending',
            isFollowed: true,
          ),
        ),
      );

      expect(find.text(UITextConstants.joinPending), findsOneWidget);
      expect(find.text(UITextConstants.followedCircle), findsOneWidget);
    });
  });

  group('CircleActionBar - 交互契约', () {
    testWidgets('visitor 点击关注圈子触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            isFollowed: false,
            onFollow: () => called = true,
          ),
        ),
      );

      await tester.tap(find.text(UITextConstants.followCircle));
      await tester.pump();

      expect(called, isTrue);
    });

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

      await tester.tap(find.text(UITextConstants.joinCircle));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('member 点击圈聊触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.member,
            joinStatus: 'joined',
            hasConversation: true,
            onOpenChat: () => called = true,
          ),
        ),
      );

      await tester.tap(find.text(UITextConstants.circleGroups));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('owner 点击编辑圈子触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.owner,
            joinStatus: 'joined',
            onEditCircle: () => called = true,
          ),
        ),
      );

      await tester.tap(find.text(UITextConstants.editCircle));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('owner 点击管理中心触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          CircleActionBar(
            isDark: false,
            role: CircleRole.owner,
            joinStatus: 'joined',
            onManageCenter: () => called = true,
          ),
        ),
      );

      await tester.tap(find.text(UITextConstants.manageCenter));
      await tester.pump();

      expect(called, isTrue);
    });
  });

  group('CircleActionBar - 稳定性', () {
    testWidgets('未知 joinStatus 安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'unknown_status',
          ),
        ),
      );

      expect(find.byType(CircleActionBar), findsOneWidget);
      expect(find.text(UITextConstants.joinCircle), findsOneWidget);
    });
  });
}
