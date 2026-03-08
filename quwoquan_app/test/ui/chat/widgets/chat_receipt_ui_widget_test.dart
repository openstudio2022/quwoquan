import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

Widget _wrapBubble({
  required Map<String, dynamic> message,
  bool isRight = true,
  bool receiptEnabled = false,
  int memberCount = 2,
}) {
  return MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: ChatMessageBubble(
          message: message,
          isRight: isRight,
          bubbleColor: Colors.blue.shade100,
          textColor: Colors.black,
          isSelectionMode: false,
          isSelected: false,
          onLongPressStart: (_) {},
          receiptEnabled: receiptEnabled,
          memberCount: memberCount,
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约 — 已读回执 UI
  // ──────────────────────────────────────────────────────────────────
  group('ChatReceiptUI — 渲染契约', () {
    testWidgets('已读消息显示双勾图标', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '已读消息',
        'senderId': 'user_001',
        'isRead': true,
      };
      await tester.pumpWidget(_wrapBubble(
        message: message,
        isRight: true,
        receiptEnabled: true,
        memberCount: 2,
      ));
      await tester.pump();

      expect(find.byIcon(Icons.done_all), findsOneWidget);
    });

    testWidgets('未读消息显示单勾图标', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '未读消息',
        'senderId': 'user_001',
        'isRead': false,
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.byIcon(Icons.done), findsOneWidget);
    });

    testWidgets('左侧消息（对方发送）不显示回执图标', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '对方消息',
        'senderId': 'user_002',
        'isRead': true,
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: false));
      await tester.pump();

      expect(find.byIcon(Icons.done_all), findsNothing);
      expect(find.byIcon(Icons.done), findsNothing);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约 — 回执与群组规模
  // ──────────────────────────────────────────────────────────────────
  group('ChatReceiptUI — 交互契约', () {
    testWidgets('小群(≤50人)右侧文本消息显示回执', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '小群消息',
        'senderId': 'user_001',
        'isRead': false,
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.byIcon(Icons.done), findsOneWidget);
    });

    testWidgets('图片消息也显示回执图标', (tester) async {
      final message = <String, dynamic>{
        'type': 'image',
        'content': '',
        'senderId': 'user_001',
        'isRead': true,
        'imageUrl': 'https://example.com/img.jpg',
      };
      await tester.pumpWidget(_wrapBubble(
        message: message,
        isRight: true,
        receiptEnabled: true,
        memberCount: 2,
      ));
      await tester.pump();

      expect(find.byIcon(Icons.done_all), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ChatReceiptUI — 错误态渲染', () {
    testWidgets('isRead 缺失时安全渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '无 isRead 字段',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
      expect(find.byIcon(Icons.done), findsOneWidget);
    });

    testWidgets('非文本/图片类型不显示回执', (tester) async {
      final message = <String, dynamic>{
        'type': 'task_card',
        'content': '任务',
        'senderId': 'user_001',
        'isRead': true,
        'tasks': <dynamic>[],
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
      expect(find.byIcon(Icons.done_all), findsNothing);
    });

    testWidgets('空 map 消息安全渲染回执区域', (tester) async {
      await tester.pumpWidget(_wrapBubble(
        message: const <String, dynamic>{},
        isRight: true,
      ));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });
  });
}
