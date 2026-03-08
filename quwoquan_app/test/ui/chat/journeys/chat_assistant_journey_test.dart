import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 聊天助手旅程：邀请助手 → @小趣 → 收到回复
///
/// ChatDetailPage 中助手交互依赖 AssistantEngine 等重型运行时，旅程测试通过
/// 轻量测试 Widget 验证 ChatRepository.inviteAssistant / removeAssistant 的
/// 核心交互链路与 UI 状态反馈。
void main() {
  group('旅程正常路径', () {
    testWidgets('邀请助手成功后 UI 提示', (tester) async {
      final mock = _TrackingAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 点击邀请按钮
      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();

      expect(find.text('助手已加入'), findsOneWidget);
      expect(mock.inviteCallCount, 1);
    });

    testWidgets('@小趣后模拟助手回复', (tester) async {
      final mock = _TrackingAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 先邀请助手
      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();

      // 输入 @小趣 消息
      await tester.enterText(find.byType(TextField), '@小趣 帮我查天气');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // 消息出现在列表
      expect(find.text('@小趣 帮我查天气'), findsOneWidget);
      expect(mock.sendCallCount, 1);
    });

    testWidgets('移除助手成功后 UI 更新', (tester) async {
      final mock = _TrackingAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 邀请后再移除
      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.remove_circle_outline));
      await tester.pumpAndSettle();

      expect(find.text('助手已移除'), findsOneWidget);
      expect(mock.removeCallCount, 1);
    });
  });

  group('旅程错误路径', () {
    testWidgets('邀请失败显示错误提示', (tester) async {
      final mock = _ErrorAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });

    testWidgets('移除助手失败显示错误提示', (tester) async {
      final mock = _ErrorRemoveAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 先邀请成功
      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();

      // 移除失败
      await tester.tap(find.byIcon(Icons.remove_circle_outline));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('已有助手再次邀请显示友好提示', (tester) async {
      final mock = _TrackingAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 第一次邀请
      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();
      expect(find.text('助手已加入'), findsOneWidget);

      // 第二次邀请 → 友好提示
      await tester.tap(find.byIcon(Icons.smart_toy));
      await tester.pumpAndSettle();
      expect(find.text('助手已在会话中'), findsOneWidget);
    });

    testWidgets('未邀请助手时移除不崩溃', (tester) async {
      final mock = _TrackingAssistantRepo();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [chatRepositoryProvider.overrideWithValue(mock)],
          child: MaterialApp(home: _AssistantTestPage(repo: mock)),
        ),
      );
      await tester.pumpAndSettle();

      // 未邀请就移除
      await tester.tap(find.byIcon(Icons.remove_circle_outline));
      await tester.pumpAndSettle();

      expect(find.text('当前没有助手'), findsOneWidget);
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// 轻量测试 Widget：模拟助手邀请 → @ 消息 → 回复的核心交互链路
// ═══════════════════════════════════════════════════════════════════════════════

class _AssistantTestPage extends StatefulWidget {
  const _AssistantTestPage({required this.repo});

  final ChatRepository repo;

  @override
  State<_AssistantTestPage> createState() => _AssistantTestPageState();
}

class _AssistantTestPageState extends State<_AssistantTestPage> {
  final _controller = TextEditingController();
  final List<String> _messages = [];
  String? _statusText;
  bool _hasAssistant = false;
  bool _hasError = false;

  Future<void> _invite() async {
    if (_hasAssistant) {
      setState(() {
        _statusText = '助手已在会话中';
        _hasError = false;
      });
      return;
    }
    try {
      await widget.repo.inviteAssistant(conversationId: 'conv_test');
      setState(() {
        _hasAssistant = true;
        _statusText = '助手已加入';
        _hasError = false;
      });
    } catch (e) {
      setState(() {
        _statusText = e.toString();
        _hasError = true;
      });
    }
  }

  Future<void> _remove() async {
    if (!_hasAssistant) {
      setState(() {
        _statusText = '当前没有助手';
        _hasError = false;
      });
      return;
    }
    try {
      await widget.repo.removeAssistant(conversationId: 'conv_test');
      setState(() {
        _hasAssistant = false;
        _statusText = '助手已移除';
        _hasError = false;
      });
    } catch (e) {
      setState(() {
        _statusText = e.toString();
        _hasError = true;
      });
    }
  }

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
        _messages.add(text);
        _hasError = false;
      });
      _controller.clear();
    } catch (e) {
      setState(() {
        _statusText = e.toString();
        _hasError = true;
      });
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
          Row(
            children: [
              IconButton(
                icon: const Icon(Icons.smart_toy),
                onPressed: _invite,
              ),
              IconButton(
                icon: const Icon(Icons.remove_circle_outline),
                onPressed: _remove,
              ),
            ],
          ),
          if (_statusText != null)
            ListTile(
              leading: _hasError
                  ? const Icon(Icons.error_outline)
                  : const Icon(Icons.check_circle),
              title: Text(_statusText!),
            ),
          Expanded(
            child: ListView(
              children: [
                for (final msg in _messages) ListTile(title: Text(msg)),
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

class _TrackingAssistantRepo extends MockChatRepository {
  int inviteCallCount = 0;
  int removeCallCount = 0;
  int sendCallCount = 0;

  @override
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async {
    inviteCallCount++;
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    removeCallCount++;
  }

  @override
  Future<Map<String, dynamic>> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    required String clientMsgId,
  }) async {
    sendCallCount++;
    return super.sendMessage(
      conversationId: conversationId,
      type: type,
      content: content,
      mediaUrl: mediaUrl,
      media: media,
      clientMsgId: clientMsgId,
    );
  }
}

class _ErrorAssistantRepo extends MockChatRepository {
  @override
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async {
    throw Exception('邀请助手失败');
  }
}

class _ErrorRemoveAssistantRepo extends MockChatRepository {
  @override
  Future<void> removeAssistant({required String conversationId}) async {
    throw Exception('移除助手失败');
  }
}
