import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

Widget _wrapBubble({
  required Map<String, dynamic> message,
  bool isRight = false,
  VoidCallback? onTap,
  void Function(LongPressStartDetails)? onLongPressStart,
  bool showFeedbackActions = false,
}) {
  return MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: ChatMessageBubble(
          message: message,
          isRight: isRight,
          bubbleColor: Colors.white,
          textColor: Colors.black,
          isSelectionMode: false,
          isSelected: false,
          onLongPressStart: onLongPressStart ?? (_) {},
          onTap: onTap,
          showFeedbackActions: showFeedbackActions,
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatMessageBubble — 渲染契约', () {
    testWidgets('文本消息正确显示 content', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '你好世界',
        'senderId': 'user_001',
        'senderName': '测试用户',
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.text('你好世界'), findsAtLeastNWidgets(1));
    });

    testWidgets('发送者名称正确显示（左侧气泡）', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '一条消息',
        'senderId': 'user_002',
        'senderName': '李明',
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: false));
      await tester.pump();

      expect(find.text('李明'), findsOneWidget);
    });

    testWidgets('ChatMessageBubble widget 正确渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '测试消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('完整 card fence 渲染为用户可见内容而不是源码残片', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content':
            '## 华为云盘古分析\n\n```card:compare\n{"title":"差异化优势","vendor":"华为云"}\n```',
        'senderId': AppConceptConstants.assistantSenderId,
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(
        find.textContaining('差异化优势', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('华为云', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('card:compare', findRichText: true),
        findsNothing,
      );
      expect(find.textContaining('```', findRichText: true), findsNothing);
    });

    testWidgets('非法 card fence 不会把 markdown 源码泄漏到界面', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content':
            '## 查询结论\n\n```card:unknown\n{"title":"内部协议","vendor":"Cursor"}\n```\n\n最终结论仍然保留。',
        'senderId': AppConceptConstants.assistantSenderId,
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(
        find.textContaining('最终结论仍然保留。', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('card:unknown', findRichText: true),
        findsNothing,
      );
      expect(
        find.textContaining('内部协议', findRichText: true),
        findsNothing,
      );
      expect(find.textContaining('```', findRichText: true), findsNothing);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatMessageBubble — 交互契约', () {
    testWidgets('长按消息气泡触发 onLongPressStart', (tester) async {
      var longPressed = false;
      final message = <String, dynamic>{
        'type': 'text',
        'content': '长按测试消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          isRight: true,
          onLongPressStart: (_) => longPressed = true,
        ),
      );
      await tester.pump();

      final bubble = tester.widget<ChatMessageBubble>(
        find.byType(ChatMessageBubble),
      );
      bubble.onLongPressStart(const LongPressStartDetails());
      await tester.pump();

      expect(longPressed, isTrue);
    });

    testWidgets('tap 消息气泡触发 onTap', (tester) async {
      var tapped = false;
      final message = <String, dynamic>{
        'type': 'text',
        'content': '点击测试消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          isRight: true,
          onTap: () => tapped = true,
        ),
      );
      await tester.pump();

      final bubble = tester.widget<ChatMessageBubble>(
        find.byType(ChatMessageBubble),
      );
      bubble.onTap!();
      await tester.pump();

      expect(tapped, isTrue);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ChatMessageBubble — 错误态渲染', () {
    testWidgets('空 content 安全渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('null content 安全渲染', (tester) async {
      final message = <String, dynamic>{'type': 'text', 'senderId': 'user_001'};
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('空 message map 安全渲染', (tester) async {
      await tester.pumpWidget(_wrapBubble(message: const {}));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('未知 type 安全渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'unknown_type_xyz',
        'content': '未知类型消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });
  });
}
