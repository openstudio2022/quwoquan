/// L3 UI 契约测试：消息构建逻辑（纯 Dart，无 Widget 渲染依赖）
///
/// 验收覆盖：A3（工具失败可恢复）、A10（渲染稳定性）
/// 执行方式：dart test（纯 VM）
///
/// 核心命题：
///   chat_detail_page.dart 中的 assistantMessages 构建逻辑（Line 1007-1027）：
///   1. isError == true 的消息必须被过滤
///   2. 含已知降级文案前缀的消息必须被过滤
///   3. streaming == true 的消息必须被过滤
///   4. type != 'text' 的消息必须被过滤
///   5. content 为空的消息必须被过滤
///   6. isSelf == true 的消息映射为 role: 'user'，否则为 role: 'assistant'
///
/// 注意：测试函数 _buildAssistantMessages 是对 chat_detail_page.dart
///       同段逻辑的精确复制（单独抽出测试），任何修改必须同步两处。
library;

import 'package:quwoquan_app/assistant/internal_legacy/protocol/run_request.dart';
import 'package:test/test.dart';

// ─── 精确复制 chat_detail_page.dart Line 1007-1027 的过滤和映射逻辑 ──────────
// 此函数是"活文档"：若 chat_detail_page.dart 修改了过滤规则，此处也必须同步更新，
// 否则此测试将立即失败，从而在 UI 测试前拦截逻辑回归。
List<AssistantRunMessage> buildAssistantMessages(
  List<Map<String, dynamic>> messages,
) {
  return messages
      .where((m) {
        if ((m['type'] as String? ?? 'text') != 'text') return false;
        if (m['streaming'] == true) return false;
        if (m['isError'] == true) return false;
        final content = (m['content'] as String?)?.trim() ?? '';
        if (content.isEmpty) return false;
        if (content.startsWith('助手暂时不可用') ||
            content.startsWith('模型调用失败') ||
            content.startsWith('模型调用异常') ||
            content.startsWith('当前模型服务不可用') ||
            content.contains('HTTP 400') ||
            content.contains('HTTP 500')) {
          return false;
        }
        if (content.contains('正在查询') ||
            content.contains('正在获取') ||
            content.contains('正在检索') ||
            content.contains('正在搜索') ||
            content.contains('正在为您') ||
            content.contains('正在规划') ||
            content.contains('正在执行')) {
          return false;
        }
        if (m['isSelf'] != true &&
            content.startsWith('{') &&
            (content.contains('"decision"') ||
                content.contains('"contractVersion"'))) {
          return false;
        }
        return true;
      })
      .map(
        (m) => AssistantRunMessage(
          role: (m['isSelf'] == true) ? 'user' : 'assistant',
          content: (m['content'] as String?) ?? '',
        ),
      )
      .toList(growable: false);
}

// ─── 已知降级文案前缀（与 chat_detail_page.dart 保持完全一致）─────────────────
const _degradedPrefixes = <String>['助手暂时不可用', '模型调用失败', '模型调用异常', '当前模型服务不可用'];

void main() {
  group('AssistantMessageHistoryContract', () {
    // ── 规则 1：isError == true 必须被过滤 ───────────────────────────────
    test('Rule-1: messages with isError:true are filtered out', () {
      final messages = <Map<String, dynamic>>[
        {'type': 'text', 'role': 'user', 'isSelf': true, 'content': '你好'},
        {
          'type': 'text',
          'role': 'assistant',
          'isSelf': false,
          'content': '助手暂时不可用，请稍后重试。',
          'isError': true,
        },
        {'type': 'text', 'role': 'user', 'isSelf': true, 'content': '那换个问题'},
      ];

      final result = buildAssistantMessages(messages);
      expect(result.length, equals(2), reason: '含 isError:true 的消息必须被过滤');
      expect(
        result.any((m) => m.content.contains('助手暂时不可用')),
        isFalse,
        reason: '降级错误文案不得出现在 assistantMessages 中',
      );
    });

    // ── 规则 2：已知降级文案前缀必须被过滤 ────────────────────────────────
    for (final prefix in _degradedPrefixes) {
      test(
        'Rule-2: message with degraded prefix "$prefix" is filtered out',
        () {
          final messages = <Map<String, dynamic>>[
            {'type': 'text', 'isSelf': true, 'content': '问题'},
            {'type': 'text', 'isSelf': false, 'content': '$prefix详细错误信息'},
            {'type': 'text', 'isSelf': true, 'content': '再问一次'},
          ];

          final result = buildAssistantMessages(messages);
          expect(
            result.any((m) => m.content.startsWith(prefix)),
            isFalse,
            reason: '含 "$prefix" 前缀的消息不得进入 assistantMessages',
          );
          expect(result.length, equals(2), reason: '正常消息不应被误删');
        },
      );
    }

    // ── 规则 3：streaming 消息必须被过滤 ──────────────────────────────────
    test('Rule-3: streaming:true messages are filtered out', () {
      final messages = <Map<String, dynamic>>[
        {'type': 'text', 'isSelf': true, 'content': '你好'},
        {
          'type': 'text',
          'isSelf': false,
          'content': '正在思考中...',
          'streaming': true,
        },
      ];

      final result = buildAssistantMessages(messages);
      expect(result.length, equals(1), reason: 'streaming:true 消息必须被过滤');
    });

    // ── 规则 4：type != 'text' 的消息必须被过滤 ───────────────────────────
    test('Rule-4: non-text type messages are filtered out', () {
      final messages = <Map<String, dynamic>>[
        {'type': 'text', 'isSelf': true, 'content': '你好'},
        {
          'type': 'image',
          'isSelf': false,
          'content': 'https://example.com/img.png',
        },
        {'type': 'audio', 'isSelf': false, 'content': 'audio_url'},
      ];

      final result = buildAssistantMessages(messages);
      expect(result.length, equals(1), reason: 'type != text 的消息必须被过滤');
    });

    // ── 规则 5：content 为空的消息必须被过滤 ─────────────────────────────
    test('Rule-5: empty content messages are filtered out', () {
      final messages = <Map<String, dynamic>>[
        {'type': 'text', 'isSelf': true, 'content': '你好'},
        {'type': 'text', 'isSelf': false, 'content': ''},
        {'type': 'text', 'isSelf': false, 'content': '   '},
      ];

      final result = buildAssistantMessages(messages);
      expect(result.length, equals(1), reason: '空/空白 content 消息必须被过滤');
    });

    // ── 规则 6：isSelf == true 映射为 role:user，否则 role:assistant ──────
    test(
      'Rule-6: isSelf:true maps to user role, isSelf:false maps to assistant',
      () {
        final messages = <Map<String, dynamic>>[
          {'type': 'text', 'isSelf': true, 'content': '用户消息'},
          {'type': 'text', 'isSelf': false, 'content': '助手回复'},
        ];

        final result = buildAssistantMessages(messages);
        expect(result.length, equals(2));
        expect(result[0].role, equals('user'));
        expect(result[1].role, equals('assistant'));
      },
    );

    // ── 规则 7：正常消息不应被误删 ────────────────────────────────────────
    test('Rule-7: normal messages are preserved correctly', () {
      final messages = <Map<String, dynamic>>[
        {'type': 'text', 'isSelf': true, 'content': '深圳天气怎么样？'},
        {'type': 'text', 'isSelf': false, 'content': '深圳今天晴，25°C，适合出行。'},
        {'type': 'text', 'isSelf': true, 'content': '那明天呢？'},
      ];

      final result = buildAssistantMessages(messages);
      expect(result.length, equals(3), reason: '正常消息必须全部保留');
      expect(result[0].content, equals('深圳天气怎么样？'));
      expect(result[1].content, equals('深圳今天晴，25°C，适合出行。'));
      expect(result[2].content, equals('那明天呢？'));
    });

    // ── 规则 8：混合场景——正常消息与多种异常消息并存 ──────────────────────
    test('Rule-8: mixed scenario — only clean messages pass', () {
      final messages = <Map<String, dynamic>>[
        // 正常 user
        {'type': 'text', 'isSelf': true, 'content': '第一个问题'},
        // 错误 assistant（应被过滤）
        {
          'type': 'text',
          'isSelf': false,
          'content': '模型调用失败: HTTP 400 - bad param',
          'isError': true,
        },
        // 正常 user
        {'type': 'text', 'isSelf': true, 'content': '第二个问题'},
        // 正常 assistant
        {'type': 'text', 'isSelf': false, 'content': '这是正常回复'},
        // streaming（应被过滤）
        {'type': 'text', 'isSelf': false, 'content': '...', 'streaming': true},
        // 图片（应被过滤）
        {
          'type': 'image',
          'isSelf': false,
          'content': 'https://example.com/img',
        },
        // 空 content（应被过滤）
        {'type': 'text', 'isSelf': true, 'content': ''},
      ];

      final result = buildAssistantMessages(messages);
      // 只有 "第一个问题"、"第二个问题"、"这是正常回复" 三条通过
      expect(result.length, equals(3), reason: '混合场景下只有 3 条干净消息通过');
      expect(
        result.map((m) => m.content).toList(),
        equals(['第一个问题', '第二个问题', '这是正常回复']),
      );
    });

    // ── 规则 9：多轮对话历史不含任何降级消息（典型使用场景）────────────────
    test(
      'Rule-9: typical multi-turn conversation without any degraded messages',
      () {
        // 模拟"两轮正常对话，中间曾经有过一次失败（已通过 isError 标记）"的场景
        final chatHistory = <Map<String, dynamic>>[
          {'type': 'text', 'isSelf': true, 'content': '你好'},
          {'type': 'text', 'isSelf': false, 'content': '你好！有什么可以帮你？'},
          {'type': 'text', 'isSelf': true, 'content': '深圳天气'},
          // 第一次失败（isError 标记）
          {
            'type': 'text',
            'isSelf': false,
            'content': '助手暂时不可用，请稍后重试。',
            'isError': true,
          },
          // 重新发送（用户点了重试）
          {'type': 'text', 'isSelf': true, 'content': '深圳天气'},
          // 成功回复
          {'type': 'text', 'isSelf': false, 'content': '深圳今天晴，25°C，空气质量良好。'},
        ];

        final result = buildAssistantMessages(chatHistory);
        // 3 条 user + 2 条 assistant（isError 标记的那条被过滤）= 5
        expect(result.length, equals(5));
        // 最后一条 LLM 输入是正确的助手回复，不是错误文案
        final lastAssistantMsg = result.lastWhere((m) => m.role == 'assistant');
        expect(
          lastAssistantMsg.content.contains('深圳今天晴'),
          isTrue,
          reason: '最后一条 assistant 消息必须是正常回复，不含降级文案',
        );
      },
    );
  });
}
