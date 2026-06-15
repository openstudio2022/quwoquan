import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('CircleActionBar - 首屏 CTA 契约', () {
    testWidgets('owner 首屏不展示管理入口，只展示已加入与私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.owner,
            joinStatus: 'joined',
            hasConversation: true,
          ),
        ),
      );

      expect(find.text(UITextConstants.joinedCircle), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.editCircle), findsNothing);
      expect(find.text(UITextConstants.manageCenter), findsNothing);
    });

    testWidgets('visitor 默认显示加入和私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
          ),
        ),
      );

      expect(find.text(UITextConstants.joinCircle), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.followCircle), findsNothing);
    });

    testWidgets('审批圈子 visitor 显示申请加入和私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: false,
            role: CircleRole.visitor,
            joinStatus: 'none',
            joinPolicy: 'approval',
          ),
        ),
      );

      expect(find.text(UITextConstants.circleJoinApproval), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
    });

    testWidgets('待审核态显示加入审批中和私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleActionBar(
            isDark: true,
            role: CircleRole.visitor,
            joinStatus: 'pending',
          ),
        ),
      );

      expect(find.text(UITextConstants.joinPending), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
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

      await tester.tap(find.text(UITextConstants.joinCircle));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('有会话时点击私信触发回调', (tester) async {
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

      await tester.tap(find.text(UITextConstants.profileDirectMessage));
      await tester.pump();

      expect(called, isTrue);
    });
  });
}
