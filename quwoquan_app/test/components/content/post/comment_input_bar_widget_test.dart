/// L1b Widget 测试：CommentInputBar（评论输入组件）
///
/// 三维度覆盖：
///   渲染契约  — 组件正确渲染，submit 按钮可见
///   交互契约  — 空输入时 submit 禁用；输入文本后 submit 启用
///   边界      — 清空文本后恢复禁用状态
///
/// mock.yaml dart_func:
///   - testCommentInputBarSubmitDisabledWhenEmpty
///   - testCommentInputBarSubmitEnabledAfterInput
///
/// NOTE: 当 lib/components/comment_system/comment_input_bar.dart 实现后，
/// 替换此文件中的 _TestableCommentBar 为实际组件引用。
/// 该实际组件应使用相同的 TestKeys (commentInputBar, commentTextField, submitCommentButton)。
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/test_keys.dart';

// ─── testable stub ─────────────────────────────────────────────────────────────
//
// _TestableCommentBar 是用于测试的最小实现，遵循与真实 CommentInputBar 相同的
// TestKeys 规范。当真实 CommentInputBar 实现后，可直接替换本 stub。

class _TestableCommentBar extends StatefulWidget {
  const _TestableCommentBar({required this.onSubmit});
  final void Function(String text) onSubmit;

  @override
  State<_TestableCommentBar> createState() => _TestableCommentBarState();
}

class _TestableCommentBarState extends State<_TestableCommentBar> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canSubmit = _controller.text.trim().isNotEmpty;
    return Container(
      key: TestKeys.commentInputBar,
      padding: const EdgeInsets.all(8),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              key: TestKeys.commentTextField,
              controller: _controller,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(hintText: '写下你的评论…'),
            ),
          ),
          const SizedBox(width: 8),
          ElevatedButton(
            key: TestKeys.submitCommentButton,
            onPressed: canSubmit ? () => widget.onSubmit(_controller.text) : null,
            child: const Text('发送'),
          ),
        ],
      ),
    );
  }
}

// ─── helper ───────────────────────────────────────────────────────────────────

Widget _wrapBar({required void Function(String) onSubmit}) {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        home: Scaffold(body: _TestableCommentBar(onSubmit: onSubmit)),
      ),
    ),
  );
}

// ── dart_func 实现（mock.yaml: widget_scenarios）──────────────────────────────

/// mock.yaml dart_func: testCommentInputBarSubmitDisabledWhenEmpty
///
/// 交互契约：评论文本框为空时，提交按钮处于禁用状态（onPressed == null）。
Future<void> testCommentInputBarSubmitDisabledWhenEmpty(
    WidgetTester tester) async {
  final submittedTexts = <String>[];
  await tester.pumpWidget(_wrapBar(onSubmit: (t) => submittedTexts.add(t)));

  // 验证组件渲染
  expect(find.byKey(TestKeys.commentInputBar), findsOneWidget,
      reason: 'commentInputBar 应存在于 Widget 树');
  expect(find.byKey(TestKeys.commentTextField), findsOneWidget,
      reason: 'commentTextField 应存在');
  expect(find.byKey(TestKeys.submitCommentButton), findsOneWidget,
      reason: 'submitCommentButton 应存在');

  // 空输入时 submit 应禁用（ElevatedButton.onPressed == null → onPressed 不触发）
  await tester.tap(find.byKey(TestKeys.submitCommentButton), warnIfMissed: false);
  await tester.pump();
  expect(submittedTexts, isEmpty,
      reason: '空文本时不应触发提交');
}

/// mock.yaml dart_func: testCommentInputBarSubmitEnabledAfterInput
///
/// 交互契约：输入非空文本后，提交按钮变为启用状态；点击后 onSubmit 回调被调用。
Future<void> testCommentInputBarSubmitEnabledAfterInput(
    WidgetTester tester) async {
  final submittedTexts = <String>[];
  await tester.pumpWidget(_wrapBar(onSubmit: (t) => submittedTexts.add(t)));

  // 输入文本
  await tester.enterText(find.byKey(TestKeys.commentTextField), '这张图真漂亮！');
  await tester.pump();

  // 输入后 submit 应启用 → 点击触发回调
  await tester.tap(find.byKey(TestKeys.submitCommentButton), warnIfMissed: false);
  await tester.pump();

  expect(submittedTexts, isNotEmpty,
      reason: '输入文本后点击提交应触发 onSubmit 回调');
  expect(submittedTexts.first, equals('这张图真漂亮！'),
      reason: 'onSubmit 应接收正确的文本内容');
}

// ─── tests ────────────────────────────────────────────────────────────────────

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('CommentInputBar — 渲染契约', () {
    testWidgets('renders input bar with TestKeys', (tester) async {
      await tester.pumpWidget(_wrapBar(onSubmit: (_) {}));
      await tester.pump();
      expect(find.byKey(TestKeys.commentInputBar), findsOneWidget);
      expect(find.byKey(TestKeys.commentTextField), findsOneWidget);
      expect(find.byKey(TestKeys.submitCommentButton), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约（mock.yaml dart_func 实现）
  // ──────────────────────────────────────────────────────────────────
  group('CommentInputBar — 交互契约', () {
    testWidgets(
      'testCommentInputBarSubmitDisabledWhenEmpty: 空输入时提交禁用',
      testCommentInputBarSubmitDisabledWhenEmpty,
    );

    testWidgets(
      'testCommentInputBarSubmitEnabledAfterInput: 输入文本后提交启用',
      testCommentInputBarSubmitEnabledAfterInput,
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // 边界情况
  // ──────────────────────────────────────────────────────────────────
  group('CommentInputBar — 边界情况', () {
    testWidgets('输入后清空 → 提交再次禁用', (tester) async {
      final submittedTexts = <String>[];
      await tester.pumpWidget(_wrapBar(onSubmit: (t) => submittedTexts.add(t)));

      await tester.enterText(find.byKey(TestKeys.commentTextField), '有内容');
      await tester.pump();

      await tester.enterText(find.byKey(TestKeys.commentTextField), '');
      await tester.pump();

      await tester.tap(find.byKey(TestKeys.submitCommentButton), warnIfMissed: false);
      await tester.pump();

      expect(submittedTexts, isEmpty, reason: '清空文本后提交应再次禁用');
    });

    testWidgets('仅空白字符 → 提交禁用', (tester) async {
      final submittedTexts = <String>[];
      await tester.pumpWidget(_wrapBar(onSubmit: (t) => submittedTexts.add(t)));

      await tester.enterText(find.byKey(TestKeys.commentTextField), '   ');
      await tester.pump();

      await tester.tap(find.byKey(TestKeys.submitCommentButton), warnIfMissed: false);
      await tester.pump();

      expect(submittedTexts, isEmpty, reason: '仅空白字符时提交应禁用');
    });
  });
}
