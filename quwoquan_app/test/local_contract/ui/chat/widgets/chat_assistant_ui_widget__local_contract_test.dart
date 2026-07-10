import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_answer_toolbar.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/regenerate_options_popup.dart';

Widget _wrapToolbar({
  String feedbackStatus = '',
  VoidCallback? onFeedbackHelpful,
  VoidCallback? onFeedbackUnhelpful,
  VoidCallback? onCopyAnswer,
  VoidCallback? onShareAnswer,
  void Function(RegenerateOption)? onRegenerateSelected,
}) {
  return MaterialApp(
    home: Scaffold(
      body: AssistantAnswerToolbar(
        feedbackStatus: feedbackStatus,
        onFeedbackHelpful: onFeedbackHelpful,
        onFeedbackUnhelpful: onFeedbackUnhelpful,
        onCopyAnswer: onCopyAnswer,
        onShareAnswer: onShareAnswer,
        onRegenerateSelected: onRegenerateSelected,
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('AssistantAnswerToolbar — 渲染契约', () {
    testWidgets('Toolbar 正确渲染 5 个按钮区域', (tester) async {
      await tester.pumpWidget(_wrapToolbar());
      await tester.pump();

      expect(find.byType(AssistantAnswerToolbar), findsOneWidget);
      expect(find.bySemanticsLabel('有帮助'), findsOneWidget);
      expect(find.bySemanticsLabel('没帮助'), findsOneWidget);
      expect(find.bySemanticsLabel('复制'), findsOneWidget);
      expect(find.bySemanticsLabel('转发'), findsOneWidget);
    });

    testWidgets('feedbackStatus=helpful 时有帮助图标为填充态', (tester) async {
      await tester.pumpWidget(_wrapToolbar(feedbackStatus: 'helpful'));
      await tester.pump();

      expect(
        find.byIcon(CupertinoIcons.hand_thumbsup_fill),
        findsOneWidget,
      );
      expect(
        find.byIcon(CupertinoIcons.hand_thumbsdown),
        findsOneWidget,
      );
    });

    testWidgets('feedbackStatus=unhelpful 时没帮助图标为填充态', (tester) async {
      await tester.pumpWidget(_wrapToolbar(feedbackStatus: 'unhelpful'));
      await tester.pump();

      expect(
        find.byIcon(CupertinoIcons.hand_thumbsdown_fill),
        findsOneWidget,
      );
      expect(
        find.byIcon(CupertinoIcons.hand_thumbsup),
        findsOneWidget,
      );
    });

    testWidgets('重新生成按钮渲染', (tester) async {
      await tester.pumpWidget(_wrapToolbar());
      await tester.pump();

      expect(
        find.byIcon(CupertinoIcons.arrow_2_circlepath),
        findsOneWidget,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('AssistantAnswerToolbar — 交互契约', () {
    testWidgets('tap 有帮助按钮触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(_wrapToolbar(
        onFeedbackHelpful: () => called = true,
      ));
      await tester.pump();

      await tester.tap(find.bySemanticsLabel('有帮助'));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('tap 没帮助按钮触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(_wrapToolbar(
        onFeedbackUnhelpful: () => called = true,
      ));
      await tester.pump();

      await tester.tap(find.bySemanticsLabel('没帮助'));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('tap 复制按钮触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(_wrapToolbar(
        onCopyAnswer: () => called = true,
      ));
      await tester.pump();

      await tester.tap(find.bySemanticsLabel('复制'));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('tap 转发按钮触发回调', (tester) async {
      var called = false;
      await tester.pumpWidget(_wrapToolbar(
        onShareAnswer: () => called = true,
      ));
      await tester.pump();

      await tester.tap(find.bySemanticsLabel('转发'));
      await tester.pump();

      expect(called, isTrue);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('AssistantAnswerToolbar — 错误态渲染', () {
    testWidgets('null 回调安全渲染', (tester) async {
      await tester.pumpWidget(_wrapToolbar(
        onFeedbackHelpful: null,
        onFeedbackUnhelpful: null,
        onCopyAnswer: null,
        onShareAnswer: null,
        onRegenerateSelected: null,
      ));
      await tester.pump();

      expect(find.byType(AssistantAnswerToolbar), findsOneWidget);
    });

    testWidgets('null 回调时 tap 有帮助不崩溃', (tester) async {
      await tester.pumpWidget(_wrapToolbar(onFeedbackHelpful: null));
      await tester.pump();

      await tester.tap(find.bySemanticsLabel('有帮助'));
      await tester.pump();

      expect(find.byType(AssistantAnswerToolbar), findsOneWidget);
    });

    testWidgets('空 feedbackStatus 安全渲染', (tester) async {
      await tester.pumpWidget(_wrapToolbar(feedbackStatus: ''));
      await tester.pump();

      expect(find.byType(AssistantAnswerToolbar), findsOneWidget);
      expect(
        find.byIcon(CupertinoIcons.hand_thumbsup),
        findsOneWidget,
      );
      expect(
        find.byIcon(CupertinoIcons.hand_thumbsdown),
        findsOneWidget,
      );
    });

    testWidgets('未知 feedbackStatus 安全渲染', (tester) async {
      await tester.pumpWidget(_wrapToolbar(feedbackStatus: 'unknown_status'));
      await tester.pump();

      expect(find.byType(AssistantAnswerToolbar), findsOneWidget);
    });
  });
}
