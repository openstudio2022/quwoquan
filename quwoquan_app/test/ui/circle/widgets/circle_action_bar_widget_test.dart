import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';

Widget _wrap(Widget child) => MaterialApp(
      home: Scaffold(body: child),
    );

void main() {
  group('CircleActionBar — 渲染契约', () {
    testWidgets('owner 角色显示编辑和管理按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.owner,
          joinStatus: 'joined',
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.editCircle), findsOneWidget);
      expect(find.text(UITextConstants.manageCenter), findsOneWidget);
      expect(find.byIcon(Icons.edit_outlined), findsOneWidget);
      expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    });

    testWidgets('admin 角色显示编辑和管理按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.admin,
          joinStatus: 'joined',
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.editCircle), findsOneWidget);
      expect(find.text(UITextConstants.manageCenter), findsOneWidget);
    });

    testWidgets('visitor 角色显示关注和加入按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'none',
          isFollowed: false,
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.follow), findsOneWidget);
      expect(find.text(UITextConstants.joinCircle), findsOneWidget);
    });

    testWidgets('已关注状态显示"已关注"', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'none',
          isFollowed: true,
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.following), findsOneWidget);
      expect(find.byIcon(Icons.check), findsOneWidget);
    });

    testWidgets('已加入状态显示"已加入圈子"', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.member,
          joinStatus: 'joined',
          isFollowed: true,
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.joinedCircle), findsOneWidget);
      expect(find.byIcon(Icons.check_circle_outline), findsOneWidget);
    });

    testWidgets('审批中状态显示"加入审批中"', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'pending',
          isFollowed: false,
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.joinPending), findsOneWidget);
      expect(find.byIcon(Icons.hourglass_top), findsOneWidget);
    });

    testWidgets('深色模式正确渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: true,
          role: CircleRole.visitor,
          joinStatus: 'none',
          isFollowed: false,
        ),
      ));
      await tester.pump();

      expect(find.byType(CircleActionBar), findsOneWidget);
      expect(find.text(UITextConstants.follow), findsOneWidget);
    });
  });

  group('CircleActionBar — 交互契约', () {
    testWidgets('visitor 点击关注按钮触发回调', (tester) async {
      bool followCalled = false;
      await tester.pumpWidget(_wrap(
        CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'none',
          isFollowed: false,
          onFollow: () => followCalled = true,
        ),
      ));
      await tester.pump();

      await tester.tap(find.text(UITextConstants.follow));
      await tester.pump();

      expect(followCalled, isTrue);
    });

    testWidgets('visitor 点击加入按钮触发回调', (tester) async {
      bool joinCalled = false;
      await tester.pumpWidget(_wrap(
        CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'none',
          isFollowed: false,
          onJoinCircle: () => joinCalled = true,
        ),
      ));
      await tester.pump();

      await tester.tap(find.text(UITextConstants.joinCircle));
      await tester.pump();

      expect(joinCalled, isTrue);
    });

    testWidgets('owner 点击编辑按钮触发回调', (tester) async {
      bool editCalled = false;
      await tester.pumpWidget(_wrap(
        CircleActionBar(
          isDark: false,
          role: CircleRole.owner,
          joinStatus: 'joined',
          onEditCircle: () => editCalled = true,
        ),
      ));
      await tester.pump();

      await tester.tap(find.text(UITextConstants.editCircle));
      await tester.pump();

      expect(editCalled, isTrue);
    });

    testWidgets('owner 点击管理中心按钮触发回调', (tester) async {
      bool manageCalled = false;
      await tester.pumpWidget(_wrap(
        CircleActionBar(
          isDark: false,
          role: CircleRole.owner,
          joinStatus: 'joined',
          onManageCenter: () => manageCalled = true,
        ),
      ));
      await tester.pump();

      await tester.tap(find.text(UITextConstants.manageCenter));
      await tester.pump();

      expect(manageCalled, isTrue);
    });
  });

  group('CircleActionBar — 错误态渲染', () {
    testWidgets('无回调时按钮安全渲染不崩溃', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'none',
          isFollowed: false,
        ),
      ));
      await tester.pump();

      expect(find.byType(CircleActionBar), findsOneWidget);
      expect(find.byType(OutlinedButton), findsWidgets);
    });

    testWidgets('未知 joinStatus 安全渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.visitor,
          joinStatus: 'unknown_status',
          isFollowed: false,
        ),
      ));
      await tester.pump();

      expect(find.byType(CircleActionBar), findsOneWidget);
      expect(find.text(UITextConstants.joinCircle), findsOneWidget);
    });

    testWidgets('member 角色显示非管理按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleActionBar(
          isDark: false,
          role: CircleRole.member,
          joinStatus: 'joined',
          isFollowed: true,
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.editCircle), findsNothing);
      expect(find.text(UITextConstants.manageCenter), findsNothing);
      expect(find.text(UITextConstants.following), findsOneWidget);
    });
  });
}
