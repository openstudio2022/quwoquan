/// L1 契约测试：消息历史协议完整性
///
/// 验收覆盖：A3（工具失败可恢复）、A8（测试覆盖可复跑）
/// 执行方式：dart test（纯 VM，无 flutter shell 依赖）
///
/// 核心命题：
///   1. SessionManager.load() 不得加载降级/错误消息（防历史污染）
///   2. SessionManager.appendMessage() 后 save()/load() 往返，结构不丢失
///   3. summarizeRecent() 不得输出 JSON envelope 原文
///   4. summarizeRecent() 不得输出已知降级文案前缀
///   5. 消息序列化往返：tool_calls / tool_call_id 字段类型保持 dynamic（不被 toString）
library;

import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:test/test.dart';

// ─── 所有已知降级文案前缀 ─────────────────────────────────────────────────────
const _degradedPrefixes = <String>[
  '模型调用失败',
  '模型调用异常',
  '助手暂时不可用',
  '当前模型服务不可用',
  '模板渲染失败',
];

// ─── JSON envelope keys ───────────────────────────────────────────────────────
const _jsonEnvelopeKeys = <String>['contractVersion'];

/// 写入 sessions.json 并用 SessionManager.load() 加载
Future<AssistantSessionManager> _loadFrom(
  Directory dir,
  Map<String, dynamic> payload,
) async {
  final file = File('${dir.path}/sessions.json');
  await file.writeAsString(jsonEncode(payload));
  final sm = AssistantSessionManager(storagePath: file.path);
  await sm.load();
  return sm;
}

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('pa_history_protocol_');
  });

  tearDown(() async {
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  // ── 规则 1：load() 必须过滤降级消息 ─────────────────────────────────────
  group('Rule-1: load() filters degraded messages', () {
    for (final prefix in _degradedPrefixes) {
      test('filters message starting with "$prefix"', () async {
        final sm = await _loadFrom(tempDir, {
          'version': 'v2',
          'activeSessionId': 'assistant',
          'sessions': {
            'assistant': [
              {'role': 'user', 'content': '深圳天气'},
              {'role': 'assistant', 'content': '$prefix: 无法获取数据'},
              {'role': 'user', 'content': '那明天呢'},
            ],
          },
          'metadata': {},
        });

        final messages = sm.getOrCreateSession('assistant');
        final assistantMsgs = messages
            .where((m) => m['role'] == 'assistant')
            .toList();

        expect(
          assistantMsgs.isEmpty,
          isTrue,
          reason: 'load() 必须过滤以"$prefix"开头的 assistant 消息',
        );
        // user 消息不应被误删
        final userMsgs = messages.where((m) => m['role'] == 'user').toList();
        expect(userMsgs.length, equals(2), reason: 'user 消息不应被过滤');
      });
    }
  });

  // ── 规则 2：load() 不误删正常 assistant 消息 ────────────────────────────
  test('Rule-2: load() preserves normal assistant messages', () async {
    const normalContent = '深圳今天晴，25°C，适合出行。';
    final sm = await _loadFrom(tempDir, {
      'version': 'v2',
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '深圳天气'},
          {'role': 'assistant', 'content': normalContent},
        ],
      },
      'metadata': {},
    });

    final messages = sm.getOrCreateSession('assistant');
    final assistantMsg = messages.firstWhere((m) => m['role'] == 'assistant');
    expect(
      assistantMsg['content'],
      equals(normalContent),
      reason: '正常 assistant 消息不得被 load() 误删',
    );
  });

  // ── 规则 3：load() 保留 dynamic 值类型（不做 toString 转换）──────────────
  test(
    'Rule-3: load() preserves value types (int/bool/list stay non-String)',
    () async {
      final sm = await _loadFrom(tempDir, {
        'version': 'v2',
        'activeSessionId': 'assistant',
        'sessions': {
          'assistant': [
            {
              'role': 'assistant',
              'content': '正常回答',
              'tool_calls': [
                {'id': 'call_abc', 'function': 'web_search', 'args': {}},
              ],
              'metadata': {'retryCount': 2, 'flag': true},
            },
          ],
        },
        'metadata': {},
      });

      final messages = sm.getOrCreateSession('assistant');
      expect(messages.isNotEmpty, isTrue);
      final msg = messages.first;

      // tool_calls 必须是 List，不能被 toString() 变成字符串
      expect(
        msg['tool_calls'],
        isA<List>(),
        reason: 'tool_calls 值类型应为 List，load() 不得 toString() 转换',
      );
      // metadata 数值不得变成字符串
      final meta = msg['metadata'] as Map<String, dynamic>?;
      expect(
        meta?['retryCount'],
        isA<int>(),
        reason: 'metadata.retryCount 应为 int，不得被 toString() 转换为 String',
      );
      expect(
        meta?['flag'],
        isA<bool>(),
        reason: 'metadata.flag 应为 bool，不得被 toString() 转换为 String',
      );
    },
  );

  // ── 规则 4：appendMessage + save + load 往返不丢 content ─────────────────
  test('Rule-4: append→save→load round-trip preserves content', () async {
    final file = File('${tempDir.path}/sessions.json');
    final sm = AssistantSessionManager(storagePath: file.path);

    sm.appendMessage(sessionId: 'assistant', role: 'user', content: '你好');
    sm.appendMessage(
      sessionId: 'assistant',
      role: 'assistant',
      content: '你好！有什么可以帮你的？',
    );
    await sm.save();

    final sm2 = AssistantSessionManager(storagePath: file.path);
    await sm2.load();
    final messages = sm2.getOrCreateSession('assistant');
    expect(messages.length, equals(2));
    expect(messages[0]['role'], equals('user'));
    expect(messages[0]['content'], equals('你好'));
    expect(messages[1]['role'], equals('assistant'));
    expect(messages[1]['content'], equals('你好！有什么可以帮你的？'));
  });

  test('Rule-4b: load() keeps canonical assistant_turn summary displayable', () async {
    final canonicalTurn = jsonEncode(<String, dynamic>{
      'contractVersion': 'assistant_turn',
      'decision': const <String, dynamic>{'nextAction': 'answer'},
      'messageKind': 'answer',
      'userMarkdown': '这是可见回答',
      'result': const <String, dynamic>{'text': '这是可见回答'},
    });
    final sm = await _loadFrom(tempDir, {
      'version': 'v2',
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '给我一个结论'},
          {'role': 'assistant', 'content': canonicalTurn},
        ],
      },
      'metadata': {},
    });

    final messages = sm.getOrCreateSession('assistant');
    expect(messages[1]['content'], equals('这是可见回答'));
    expect(
      sm.summarizeRecent('assistant'),
      contains('这是可见回答'),
      reason: 'canonical assistant_turn 历史应仍能输出用户可读摘要',
    );
  });

  test('Rule-4c: save→load preserves assistant and skill-private sessions separately', () async {
    final file = File('${tempDir.path}/sessions.json');
    final sm = AssistantSessionManager(storagePath: file.path);

    sm.appendMessage(sessionId: 'assistant', role: 'user', content: '主会话问题');
    sm.appendMessage(
      sessionId: 'assistant',
      role: 'assistant',
      content: '主会话回答',
    );
    sm.appendMessage(
      sessionId: 'skill:weather',
      role: 'user',
      content: '深圳明天会下雨吗',
    );
    sm.appendMessage(
      sessionId: 'skill:weather',
      role: 'assistant',
      content: '明天有阵雨，出门记得带伞。',
    );
    sm.switchAssistantSession('skill:weather');
    await sm.save();

    final sm2 = AssistantSessionManager(storagePath: file.path);
    await sm2.load();

    expect(sm2.activeSessionId, equals('skill:weather'));
    expect(sm2.getOrCreateSession('assistant').length, equals(2));
    expect(sm2.getOrCreateSession('skill:weather').length, equals(2));
    expect(
      sm2.summarizeRecent('assistant'),
      contains('主会话回答'),
      reason: 'assistant 主会话摘要应保持自己的历史，不得被 skill 私人会话污染',
    );
    expect(
      sm2.summarizeRecent('assistant'),
      isNot(contains('带伞')),
      reason: 'assistant 主会话摘要不得混入 skill 私人会话内容',
    );
    expect(
      sm2.summarizeRecent('skill:weather'),
      contains('带伞'),
      reason: 'skill 私人会话应保持独立回放和摘要内容',
    );
  });

  // ── 规则 5：summarizeRecent() 不得输出 JSON envelope 原文 ────────────────
  test('Rule-5: summarizeRecent() must not output JSON envelope keys', () async {
    final jsonEnvelope =
        '{"contractVersion":"assistant_turn","decision":{"nextAction":"answer"},"messageKind":"answer","userMarkdown":"天气很好"}';
    final sm = await _loadFrom(tempDir, {
      'version': 'v2',
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '天气'},
          {'role': 'assistant', 'content': jsonEnvelope},
        ],
      },
      'metadata': {},
    });

    final summary = sm.summarizeRecent('assistant');
    for (final key in _jsonEnvelopeKeys) {
      expect(
        summary.contains(key),
        isFalse,
        reason: 'summarizeRecent() 不得将 JSON envelope key "$key" 输出到摘要中',
      );
    }
  });

  // ── 规则 6：summarizeRecent() 不得输出降级文案 ────────────────────────────
  test('Rule-6: summarizeRecent() must not output degraded text', () async {
    final sm = await _loadFrom(tempDir, {
      'version': 'v2',
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '你好'},
          // 这条会通过 load 过滤，不会进入内存
          {'role': 'assistant', 'content': '助手暂时不可用，请稍后重试。'},
          {'role': 'user', 'content': '那换个问题'},
        ],
      },
      'metadata': {},
    });

    final summary = sm.summarizeRecent('assistant');
    for (final prefix in _degradedPrefixes) {
      expect(
        summary.contains(prefix),
        isFalse,
        reason: 'summarizeRecent() 不得输出含降级前缀 "$prefix" 的摘要行',
      );
    }
  });

  // ── 规则 7：v1 兼容格式（无 sessions 包装层）也能正常 load ──────────────
  test('Rule-7: v1 format compatibility — root-level sessionId keys', () async {
    final normalContent = '老格式的回复内容';
    final sm = await _loadFrom(tempDir, {
      // v1: 根对象直接是 sessionId -> message[]（无 version / sessions 包装）
      'assistant': [
        {'role': 'user', 'content': '问题'},
        {'role': 'assistant', 'content': normalContent},
      ],
    });

    final messages = sm.getOrCreateSession('assistant');
    expect(
      messages.any((m) => m['content'] == normalContent),
      isTrue,
      reason: 'v1 格式 load() 必须能正确读取 assistant 消息',
    );
  });

  // ── 规则 8：load() 对空文件不崩溃 ────────────────────────────────────────
  test('Rule-8: load() with missing file does not throw', () async {
    final sm = AssistantSessionManager(
      storagePath: '${tempDir.path}/nonexistent.json',
    );
    await expectLater(sm.load(), completes);
    expect(sm.getOrCreateSession('assistant').isEmpty, isTrue);
  });

  // ── 规则 9：load() 对损坏文件安全降级，不得让运行崩溃 ────────────────────
  test('Rule-9: load() with invalid utf8/json degrades safely', () async {
    final file = File('${tempDir.path}/sessions_corrupted.json');
    await file.writeAsBytes(const <int>[0xff, 0xfe, 0xfd, 0x00]);

    final sm = AssistantSessionManager(storagePath: file.path);
    await expectLater(sm.load(), completes);
    expect(
      sm.getOrCreateSession('assistant').isEmpty,
      isTrue,
      reason: '损坏的 session 文件应被安全跳过，而不是污染内存或让加载崩溃',
    );

    await file.writeAsString('{not valid json');
    await expectLater(sm.load(), completes);
    expect(
      sm.getOrCreateSession('assistant').isEmpty,
      isTrue,
      reason: '非法 JSON 也应被安全跳过',
    );
  });
}
