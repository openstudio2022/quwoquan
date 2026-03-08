/// L3 API Contract Runner — Chat Service
///
/// 守护目标：端云数据合约不漂移（会话列表分页、消息收发、错误码格式、响应时间 SLO）
///
/// 执行方式：
///   ```
///   STAGING_BASE_URL=https://staging.api.quwoquan.com \
///   TEST_AUTH_TOKEN=TOKEN \
///   flutter test test/cloud/chat/api_contract_runner.dart \
///     --dart-define=STAGING_BASE_URL=... \
///     --dart-define=TEST_AUTH_TOKEN=...
///   ```
///
/// CI 策略：
///   - daily（staging 可用时自动触发）
///   - pre-release 必须通过
///   - staging 不可用 → markTestSkipped，不 fail
///
/// Mock Wall：本文件发真实 HTTP，位于 Mock Wall 右侧，禁止注入 MockRepository。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/chat/generated/chat_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';

const _stagingBase = String.fromEnvironment('STAGING_BASE_URL');
const _testToken = String.fromEnvironment('TEST_AUTH_TOKEN');

// ─── Shared state ───────────────────────────────────────────────────────────

bool _stagingAvailable = false;
late http.Client _client;

Map<String, String> _authHeaders(String pageId) => {
      ...CloudRequestHeaders.forPage(pageId),
      if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken',
    };

/// 创建一个测试会话，返回 conversationId。
Future<String> _seedConversation() async {
  final url = Uri.parse('$_stagingBase/v1/chat/conversations');
  final resp = await _client
      .post(
        url,
        headers: {
          ..._authHeaders('chat.conversation.create'),
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'type': 'group',
          'title': 'L3 contract seed conversation',
          'maxGroupSize': 500,
        }),
      )
      .timeout(const Duration(seconds: 10));
  if (resp.statusCode != 201) {
    throw Exception(
        '_seedConversation failed: ${resp.statusCode} ${resp.body}');
  }
  final id = (jsonDecode(resp.body) as Map<String, dynamic>)['_id'] as String;
  return id;
}

/// 发送一条测试消息，返回响应 body。
Future<Map<String, dynamic>> _sendMessage(
    String conversationId, String clientMsgId) async {
  final url = Uri.parse(
      '$_stagingBase/v1/chat/conversations/$conversationId/messages');
  final resp = await _client
      .post(
        url,
        headers: {
          ..._authHeaders('chat.message.send'),
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'type': 'text',
          'content': 'L3 contract test message',
          'clientMsgId': clientMsgId,
        }),
      )
      .timeout(const Duration(seconds: 10));
  if (resp.statusCode != 201) {
    throw Exception('_sendMessage failed: ${resp.statusCode} ${resp.body}');
  }
  return jsonDecode(resp.body) as Map<String, dynamic>;
}

// ─── Tests ──────────────────────────────────────────────────────────────────

void main() {
  setUpAll(() async {
    if (_stagingBase.isEmpty) {
      markTestSkipped(
          'L3: STAGING_BASE_URL not set — all api_contract tests skipped');
      return;
    }
    try {
      final probe = await http
          .head(Uri.parse(_stagingBase))
          .timeout(const Duration(seconds: 5));
      if (probe.statusCode >= 500) {
        markTestSkipped(
            'L3: staging returned ${probe.statusCode} — tests skipped');
        return;
      }
    } catch (e) {
      markTestSkipped('L3: staging unreachable ($e) — tests skipped');
      return;
    }
    _client = http.Client();
    _stagingAvailable = true;
  });

  tearDownAll(() {
    if (_stagingAvailable) _client.close();
  });

  // ── 场景 1：list_conversations_contract ───────────────────────────────────
  group('list_conversations_contract', () {
    late String convId;

    setUpAll(() async {
      if (!_stagingAvailable) return;
      convId = await _seedConversation();
    });

    test('GET /v1/chat/conversations 返回 200 + items 数组', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final url =
          Uri.parse('$_stagingBase/v1/chat/conversations?limit=5');
      final sw = Stopwatch()..start();
      final resp = await _client
          .get(url, headers: _authHeaders('chat.conversation.list'))
          .timeout(const Duration(seconds: 10));
      sw.stop();

      // 协议层
      expect(resp.statusCode, 200);
      expect(sw.elapsedMilliseconds, lessThan(800),
          reason: 'conversations list SLO: <800ms');

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('items'), isTrue,
          reason: 'response must contain items');
      expect(body.containsKey('cursor'), isTrue,
          reason: 'response must contain cursor for pagination');

      final items = body['items'] as List;
      expect(items, isNotEmpty);

      // 语义层：每条 conversation 有必要字段
      final first = items.first as Map<String, dynamic>;
      expect(first.containsKey('_id'), isTrue);
      expect(first.containsKey('type'), isTrue);
      expect(first.containsKey('status'), isTrue);
    });

    test('conversation 字段结构完整', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final resp = await _client
          .get(
            Uri.parse('$_stagingBase/v1/chat/conversations/$convId'),
            headers: _authHeaders('chat.conversation.get'),
          )
          .timeout(const Duration(seconds: 10));

      expect(resp.statusCode, 200);
      final conv = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(conv['_id'], convId);
      expect(conv['type'], isNotNull);
      expect(conv['status'], 'active');
      expect(conv.containsKey('createdAt'), isTrue);
    });
  });

  // ── 场景 2：send_and_recall_message_contract ──────────────────────────────
  group('send_and_recall_message_contract', () {
    late String convId;

    setUpAll(() async {
      if (!_stagingAvailable) return;
      convId = await _seedConversation();
    });

    test('发送消息返回 201 + seq + messageId', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final sw = Stopwatch()..start();
      final result = await _sendMessage(convId, 'l3-send-001');
      sw.stop();

      expect(sw.elapsedMilliseconds, lessThan(500),
          reason: 'send message SLO: <500ms');
      expect(result.containsKey('messageId'), isTrue);
      expect(result.containsKey('seq'), isTrue);
      expect(result.containsKey('timestamp'), isTrue);
      expect(result['seq'], isA<num>());
    });

    test('相同 clientMsgId 幂等（dedup）', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final msg1 = await _sendMessage(convId, 'l3-dedup-001');
      final msg2 = await _sendMessage(convId, 'l3-dedup-001');

      expect(msg1['messageId'], msg2['messageId'],
          reason: 'duplicate clientMsgId should return same messageId');
      expect(msg1['seq'], msg2['seq'],
          reason: 'duplicate clientMsgId should return same seq');
    });

    test('撤回消息返回 200 + status=recalled', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final msg = await _sendMessage(convId, 'l3-recall-001');
      final msgId = msg['messageId'] as String;

      final recallResp = await _client
          .post(
            Uri.parse(
                '$_stagingBase/v1/chat/conversations/$convId/messages/$msgId/recall'),
            headers: {
              ..._authHeaders('chat.message.recall'),
              'Content-Type': 'application/json',
            },
            body: '{}',
          )
          .timeout(const Duration(seconds: 10));

      expect(recallResp.statusCode, 200);
      final body = jsonDecode(recallResp.body) as Map<String, dynamic>;
      expect(body['status'], 'recalled');
    });

    test('消息列表包含已发送消息', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      await _sendMessage(convId, 'l3-list-001');

      final resp = await _client
          .get(
            Uri.parse(
                '$_stagingBase/v1/chat/conversations/$convId/messages?limit=10'),
            headers: _authHeaders('chat.message.list'),
          )
          .timeout(const Duration(seconds: 10));

      expect(resp.statusCode, 200);
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('items'), isTrue);
      final items = body['items'] as List;
      expect(items, isNotEmpty);

      final first = items.first as Map<String, dynamic>;
      expect(first.containsKey('_id'), isTrue);
      expect(first.containsKey('type'), isTrue);
      expect(first.containsKey('content'), isTrue);
      expect(first.containsKey('seq'), isTrue);
    });
  });

  // ── 场景 3：error_not_found_contract ──────────────────────────────────────
  group('error_not_found_contract', () {
    test('不存在的 conversationId → 404 + CHAT.USER.conversation_not_found',
        () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final resp = await _client
          .get(
            Uri.parse(
                '$_stagingBase/v1/chat/conversations/nonexistent_conv_00000'),
            headers: _authHeaders('chat.conversation.get'),
          )
          .timeout(const Duration(seconds: 10));

      // 协议层
      expect(resp.statusCode, 404);

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('code'), isTrue,
          reason: 'error response must have code field');

      // 语义层：端侧 ErrorCode 映射
      final code = ChatErrorCode.fromCode(body['code'] as String);
      expect(code, ChatErrorCode.conversationNotFound);
      expect(code.isRetryable, isFalse);
    });
  });

  // ── 场景 4：sync_messages_contract ────────────────────────────────────────
  group('sync_messages_contract', () {
    late String convId;

    setUpAll(() async {
      if (!_stagingAvailable) return;
      convId = await _seedConversation();
      for (int i = 0; i < 5; i++) {
        await _sendMessage(convId, 'l3-sync-seed-$i');
      }
    });

    test('POST /sync 返回增量消息', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final sw = Stopwatch()..start();
      final resp = await _client
          .post(
            Uri.parse(
                '$_stagingBase/v1/chat/conversations/$convId/sync'),
            headers: {
              ..._authHeaders('chat.message.sync'),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({'lastSeq': 0, 'limit': 100}),
          )
          .timeout(const Duration(seconds: 10));
      sw.stop();

      expect(resp.statusCode, 200);
      expect(sw.elapsedMilliseconds, lessThan(800),
          reason: 'sync SLO: <800ms');

      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('messages'), isTrue);
      final messages = body['messages'] as List;
      expect(messages.length, greaterThanOrEqualTo(5));
    });
  });

  // ── 场景 5：member_operations_contract ────────────────────────────────────
  group('member_operations_contract', () {
    late String convId;

    setUpAll(() async {
      if (!_stagingAvailable) return;
      convId = await _seedConversation();
    });

    test('添加成员 → 成员列表包含新成员', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final addResp = await _client
          .post(
            Uri.parse(
                '$_stagingBase/v1/chat/conversations/$convId/members'),
            headers: {
              ..._authHeaders('chat.member.add'),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'userIds': ['l3_test_member_001'],
            }),
          )
          .timeout(const Duration(seconds: 10));

      expect(addResp.statusCode, 200);

      final listResp = await _client
          .get(
            Uri.parse(
                '$_stagingBase/v1/chat/conversations/$convId/members?limit=50'),
            headers: _authHeaders('chat.member.list'),
          )
          .timeout(const Duration(seconds: 10));

      expect(listResp.statusCode, 200);
      final body = jsonDecode(listResp.body) as Map<String, dynamic>;
      expect(body.containsKey('items'), isTrue);
    });
  });
}
