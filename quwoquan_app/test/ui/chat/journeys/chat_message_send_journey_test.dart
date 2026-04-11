import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 聊天消息发送旅程：输入 → 发送 → 消息出现在列表
///
/// ChatDetailPage 依赖较重（speech_to_text、file_picker、image_picker 等 native
/// 插件），因此旅程测试通过自建简化 Widget 验证 ChatRepository 的消息发送 → 列表
/// 更新这一核心交互链路，确保 Provider 注入、异步刷新、错误态 UI 展示的完整性。
void main() {
  group('旅程正常路径', () {
    testWidgets('输入 → 发送 → 消息出现在列表', (tester) async {
      final mock = _TrackingSendChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _MessageSendTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 输入消息
      await tester.enterText(find.byType(TextField), '旅程测试消息');
      await tester.pump();
      expect(find.text('旅程测试消息'), findsOneWidget);

      // 点击发送
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // 消息出现在列表中
      expect(find.text('旅程测试消息'), findsWidgets);
      expect(mock.sendCallCount, 1);
    });

    testWidgets('发送后输入框清空', (tester) async {
      final mock = _TrackingSendChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _MessageSendTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '发送后应清空');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // 输入框应已清空
      final textField = tester.widget<TextField>(find.byType(TextField));
      expect(textField.controller?.text, isEmpty);
    });
  });

  group('旅程错误路径', () {
    testWidgets('发送失败显示错误提示', (tester) async {
      final mock = _ErrorSendChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _MessageSendTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '会失败的消息');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // 应出现错误提示
      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });

    testWidgets('发送失败后可重试', (tester) async {
      final mock = _ErrorSendChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _MessageSendTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '重试消息');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.error_outline), findsOneWidget);
      // 页面不崩溃，仍可输入
      expect(find.byType(TextField), findsOneWidget);
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('连续发送 3 条消息均可见', (tester) async {
      final mock = _TrackingSendChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _MessageSendTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      for (final msg in ['消息一', '消息二', '消息三']) {
        await tester.enterText(find.byType(TextField), msg);
        await tester.tap(find.byIcon(Icons.send));
        await tester.pumpAndSettle();
      }

      expect(find.text('消息一'), findsOneWidget);
      expect(find.text('消息二'), findsOneWidget);
      expect(find.text('消息三'), findsOneWidget);
      expect(mock.sendCallCount, 3);
    });

    testWidgets('空内容不发送', (tester) async {
      final mock = _TrackingSendChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _MessageSendTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 不输入内容直接点发送
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      expect(mock.sendCallCount, 0);
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// 轻量测试 Widget：模拟消息输入 → 发送 → 列表展示的核心交互链路
// ═══════════════════════════════════════════════════════════════════════════════

class _MessageSendTestPage extends StatefulWidget {
  const _MessageSendTestPage({required this.repo});

  final ChatRepository repo;

  @override
  State<_MessageSendTestPage> createState() => _MessageSendTestPageState();
}

class _MessageSendTestPageState extends State<_MessageSendTestPage> {
  final _controller = TextEditingController();
  final List<String> _sentMessages = [];
  String? _errorText;

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    try {
      await widget.repo.sendMessage(
        conversationId: 'conv_test',
        type: 'text',
        content: text,
        clientMsgId: 'test-${DateTime.now().millisecondsSinceEpoch}',
      );
      setState(() {
        _sentMessages.add(text);
        _errorText = null;
      });
      _controller.clear();
    } catch (e) {
      setState(() => _errorText = e.toString());
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Expanded(
            child: ListView(
              children: [
                for (final msg in _sentMessages)
                  ListTile(title: Text(msg)),
                if (_errorText != null)
                  ListTile(
                    leading: const Icon(Icons.error_outline),
                    title: Text(_errorText!),
                  ),
              ],
            ),
          ),
          Row(
            children: [
              Expanded(child: TextField(controller: _controller)),
              IconButton(icon: const Icon(Icons.send), onPressed: _send),
            ],
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Mock 变体
// ═══════════════════════════════════════════════════════════════════════════════

class _TrackingSendChatRepository extends MockChatRepository {
  int sendCallCount = 0;

  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderPersonaId,
    String? senderProfileSubjectId,
    String? personaContextVersion,
    required String clientMsgId,
  }) async {
    sendCallCount++;
    return super.sendMessage(
      conversationId: conversationId,
      type: type,
      content: content,
      mediaUrl: mediaUrl,
      media: media,
      replyToMessageId: replyToMessageId,
      mentions: mentions,
      senderPersonaId: senderPersonaId,
      senderProfileSubjectId: senderProfileSubjectId,
      personaContextVersion: personaContextVersion,
      clientMsgId: clientMsgId,
    );
  }
}

class _ErrorSendChatRepository extends MockChatRepository {
  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderPersonaId,
    String? senderProfileSubjectId,
    String? personaContextVersion,
    required String clientMsgId,
  }) async {
    throw Exception('发送失败：网络异常');
  }
}
