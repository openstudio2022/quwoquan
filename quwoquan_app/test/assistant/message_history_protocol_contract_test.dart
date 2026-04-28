library;

import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/assistant_session_history_state.dart';
import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:test/test.dart';

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

Future<Map<String, dynamic>> _readStoredPayload(Directory dir) async {
  final file = File('${dir.path}/sessions.json');
  final raw = jsonDecode(await file.readAsString());
  return (raw as Map).cast<String, dynamic>();
}

AssistantJourney _canonicalJourney() {
  return const AssistantJourney(
    stages: <AssistantJourneyStage>[
      AssistantJourneyStage(
        stageId: JourneyStageId.analyze,
        status: JourneyStageStatus.completed,
        order: 0,
        summary: '我先把问题边界理清',
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.search,
        status: JourneyStageStatus.completed,
        order: 1,
        summary: '我补充核对了关键来源',
        referenceCount: 1,
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.verify,
        status: JourneyStageStatus.completed,
        order: 2,
        summary: '我交叉确认了结论',
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.answer,
        status: JourneyStageStatus.completed,
        order: 3,
        summary: '已为你整理好',
      ),
    ],
    entries: <AssistantJourneyEntry>[
      AssistantJourneyEntry(
        entryId: 'journey.analyze',
        stageId: JourneyStageId.analyze,
        kind: JourneyEntryKind.narrative,
        status: JourneyStageStatus.completed,
        order: 0,
        headline: '我先把问题边界理清',
      ),
      AssistantJourneyEntry(
        entryId: 'journey.search',
        stageId: JourneyStageId.search,
        kind: JourneyEntryKind.referenceBundle,
        status: JourneyStageStatus.completed,
        order: 1,
        headline: '我补充核对了关键来源',
        references: <AssistantJourneyReference>[
          AssistantJourneyReference(
            title: '深圳气象台',
            url: 'https://weather.example.com/shenzhen',
            source: '官方',
          ),
        ],
      ),
      AssistantJourneyEntry(
        entryId: 'journey.verify',
        stageId: JourneyStageId.verify,
        kind: JourneyEntryKind.narrative,
        status: JourneyStageStatus.completed,
        order: 2,
        headline: '我交叉确认了结论',
      ),
      AssistantJourneyEntry(
        entryId: 'journey.answer',
        stageId: JourneyStageId.answer,
        kind: JourneyEntryKind.milestone,
        status: JourneyStageStatus.completed,
        order: 3,
        headline: '已为你整理好',
      ),
    ],
    summary: '已深度思考，参考 1 篇资料，用时 4 秒',
    referenceSummary: AssistantJourneyReferenceSummary(
      count: 1,
      references: <AssistantJourneyReference>[
        AssistantJourneyReference(
          title: '深圳气象台',
          url: 'https://weather.example.com/shenzhen',
          source: '官方',
        ),
      ],
    ),
    readiness: AssistantJourneyReadiness(finalAnswerReady: true),
  );
}

Map<String, dynamic> _canonicalAssistantMessage({
  String content = '深圳今天晴，25°C，适合出行。',
  String? id,
  String? timestamp,
  String? sourceQuery,
  String? understandingSummary,
}) {
  final journey = _canonicalJourney();
  final runArtifacts = <String, dynamic>{
    'journey': journey.toJson(),
    'answerDecision': const <String, dynamic>{
      'nextAction': 'answer',
      'finalAnswerMode': 'full',
    },
    if ((understandingSummary ?? '').trim().isNotEmpty)
      'understandingSnapshot': <String, dynamic>{
        'userFacingSummary': understandingSummary!.trim(),
      },
  };
  return <String, dynamic>{
    'role': 'assistant',
    if ((id ?? '').trim().isNotEmpty) 'id': id!.trim(),
    if ((timestamp ?? '').trim().isNotEmpty) 'timestamp': timestamp!.trim(),
    if ((sourceQuery ?? '').trim().isNotEmpty)
      'sourceQuery': sourceQuery!.trim(),
    'content': content,
    ...buildPersistedAssistantTurnFields(
      journey: journey,
      processTimeline: buildProcessTimelineFramesFromJourneyFallback(journey),
      displayMarkdown: content,
      displayPlainText: content,
      followupPrompt: '要不要我顺便看下今晚体感和穿衣建议？',
      actionHints: const <String>['看今晚天气', '看未来两天'],
      elapsedMs: 4200,
    ),
    'runArtifacts': runArtifacts,
  };
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

  test('Rule-1: load() 会清空旧版历史存储', () async {
    final sm = await _loadFrom(tempDir, {
      'version': 'v2',
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '深圳天气'},
          {'role': 'assistant', 'content': '老历史回答'},
        ],
      },
      'metadata': {},
    });

    expect(sm.sessions, isEmpty, reason: '旧版历史不再兼容，应在 load() 时被清空');
    final stored = await _readStoredPayload(tempDir);
    expect(stored['version'], equals(assistantHistoryStorageVersion));
    expect(stored['sessions'], isEmpty);
  });

  test('Rule-2: load() 保留 canonical assistant 历史并以 timeline 恢复', () async {
    final sm = await _loadFrom(tempDir, {
      'version': assistantHistoryStorageVersion,
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '深圳天气'},
          _canonicalAssistantMessage(),
        ],
      },
      'metadata': {
        'assistant': {
          'topicTitle': '深圳天气',
          'updatedAt': DateTime.now().toIso8601String(),
        },
      },
    });

    final messages = sm.getOrCreateSession('assistant');
    expect(messages.length, equals(2));
    final assistantMsg = messages.last;
    expect(assistantMsg.containsKey('assistantTurnSchemaVersion'), isFalse);
    expect(
      (assistantMsg[assistantProcessTimelineField] as List?)?.isNotEmpty,
      isTrue,
    );
    expect(
      (assistantMsg[assistantProcessTimelineField] as List?)?.length,
      equals(4),
    );
    expect(assistantMsg['streaming'], isFalse);
    expect(assistantMsg.containsKey('streamFinalAnswer'), isFalse);
  });

  test(
    'Rule-2b: load() 会把已完成 canonical assistant turn 的 streaming 残留清掉',
    () async {
      final sm = await _loadFrom(tempDir, {
        'version': assistantHistoryStorageVersion,
        'activeSessionId': 'assistant',
        'sessions': {
          'assistant': [
            {'role': 'user', 'content': '深圳天气'},
            {
              ..._canonicalAssistantMessage(),
              'streaming': true,
              'streamFinalAnswer': '正在流式输出中的旧残留',
            },
          ],
        },
        'metadata': const <String, dynamic>{},
      });

      final messages = sm.getOrCreateSession('assistant');
      expect(messages.length, equals(2));
      final assistantMsg = messages.last;
      expect(assistantMsg['streaming'], isFalse);
      expect(assistantMsg.containsKey('streamFinalAnswer'), isFalse);
      expect(
        resolvePersistedAssistantDisplayPlainText(assistantMsg),
        contains('深圳今天晴'),
      );
    },
  );

  test('Rule-2c: load() 会从旧 journey 摘要修复缺失用户消息', () async {
    final sm = await _loadFrom(tempDir, {
      'version': assistantHistoryStorageVersion,
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {
            ..._canonicalAssistantMessage(),
            'journey': {
              'stages': [
                {
                  'stageId': 'analyze',
                  'status': 'completed',
                  'summary': '我先确认你的核心问题：比较三家云厂商的 AI 能力',
                },
              ],
            },
          },
        ],
      },
      'metadata': const <String, dynamic>{},
    });

    final messages = sm.getOrCreateSession('assistant');
    expect(messages, hasLength(2));
    expect(messages.first['role'], equals('user'));
    expect(messages.first['content'], equals('比较三家云厂商的 AI 能力'));
    expect(messages.last['role'], equals('assistant'));
  });

  test('Rule-3: 当前 v1 assistant 历史不满足 canonical schema 时整段清理', () async {
    final sm = await _loadFrom(tempDir, {
      'version': assistantHistoryStorageVersion,
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '深圳天气'},
          {
            'role': 'assistant',
            'content': '看起来像正常文本，但没有 canonical journey/timeline',
          },
        ],
      },
      'metadata': {},
    });

    expect(
      sm.getOrCreateSession('assistant'),
      isEmpty,
      reason: '新版存储下不再兼容缺失 journey/uiProcessTimeline 的 assistant 历史',
    );
  });

  test(
    'Rule-4: append→save→load round-trip preserves canonical assistant turn',
    () async {
      final file = File('${tempDir.path}/sessions.json');
      final sm = AssistantSessionManager(storagePath: file.path);

      sm.appendMessage(sessionId: 'assistant', role: 'user', content: '你好');
      sm.appendMessage(
        sessionId: 'assistant',
        role: 'assistant',
        content: '深圳今天晴，25°C，适合出行。',
        metadata: _canonicalAssistantMessage(),
      );
      await sm.save();

      final sm2 = AssistantSessionManager(storagePath: file.path);
      await sm2.load();
      final messages = sm2.getOrCreateSession('assistant');
      expect(messages.length, equals(2));
      expect(messages[0]['role'], equals('user'));
      expect(messages[0]['content'], equals('你好'));
      expect(messages[1]['role'], equals('assistant'));
      expect(messages[1]['content'], equals('深圳今天晴，25°C，适合出行。'));
      expect(messages[1][assistantProcessTimelineField], isA<List<dynamic>>());
      expect(messages[1].containsKey('assistantTurnSchemaVersion'), isFalse);
    },
  );

  test('Rule-4b: appendMessage() 会为缺失或空白 timestamp 自动补值', () async {
    final sm = AssistantSessionManager(
      storagePath: '${tempDir.path}/sessions_append_timestamp.json',
    );
    await sm.load();

    sm.appendMessage(sessionId: 'assistant', role: 'user', content: '你好');
    sm.appendMessage(
      sessionId: 'assistant',
      role: 'assistant',
      content: '你好，我在。',
      metadata: const <String, dynamic>{'timestamp': '   '},
    );

    final messages = sm.getOrCreateSession('assistant');
    expect(messages, hasLength(2));
    expect((messages[0]['timestamp'] as String?)?.trim(), isNotEmpty);
    expect((messages[1]['timestamp'] as String?)?.trim(), isNotEmpty);
  });

  test('Rule-5: summarizeRecent() 只输出用户可见答案，不输出内部字段', () async {
    final sm = await _loadFrom(tempDir, {
      'version': assistantHistoryStorageVersion,
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {'role': 'user', 'content': '天气'},
          _canonicalAssistantMessage(),
        ],
      },
      'metadata': {},
    });

    final summary = sm.summarizeRecent('assistant');
    expect(summary, contains('深圳今天晴'));
    expect(summary.contains('contractId'), isFalse);
    expect(summary.contains('machineEnvelope'), isFalse);
    expect(summary.contains('{{'), isFalse);
  });

  test(
    'Rule-5b: summarizeRecent(roundsLimit) 会优先输出结构化 recent rounds transcript',
    () async {
      final sm = await _loadFrom(tempDir, {
        'version': assistantHistoryStorageVersion,
        'activeSessionId': 'assistant',
        'sessions': {
          'assistant': [
            {'role': 'user', 'content': '第一问'},
            {
              ..._canonicalAssistantMessage(content: '第一答'),
              'id': 'turn_1',
              'runArtifacts': {
                ...((_canonicalAssistantMessage(content: '第一答')['runArtifacts']
                    as Map<String, dynamic>)),
                'understandingSnapshot': const <String, dynamic>{
                  'userFacingSummary': '第一轮理解摘要',
                },
              },
            },
            {'role': 'user', 'content': '第二问'},
            {
              ..._canonicalAssistantMessage(content: '第二答'),
              'id': 'turn_2',
              'runArtifacts': {
                ...((_canonicalAssistantMessage(content: '第二答')['runArtifacts']
                    as Map<String, dynamic>)),
                'understandingSnapshot': const <String, dynamic>{
                  'userFacingSummary': '第二轮理解摘要',
                },
              },
            },
          ],
        },
        'metadata': {},
      });

      final summary = sm.summarizeRecent('assistant', roundsLimit: 1);
      expect(summary, contains('user: 第二问'));
      expect(summary, contains('understanding: 第二轮理解摘要'));
      expect(summary, contains('assistant: 第二答'));
      expect(summary, isNot(contains('第一问')));
    },
  );

  test('Rule-5d: recent rounds 会按时间窗保留 recent + older transcript', () async {
    final now = DateTime.now().toUtc();
    final olderUserTime = now.subtract(const Duration(days: 2, hours: 1));
    final olderAssistantTime = now.subtract(const Duration(days: 2));
    final recentUserTime = now.subtract(const Duration(hours: 3));
    final recentAssistantTime = now.subtract(const Duration(hours: 2));
    final sm = await _loadFrom(tempDir, {
      'version': assistantHistoryStorageVersion,
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          {
            'role': 'user',
            'content': '两天前问',
            'timestamp': olderUserTime.toIso8601String(),
          },
          _canonicalAssistantMessage(
            id: 'turn_old',
            timestamp: olderAssistantTime.toIso8601String(),
            content: '两天前答',
            understandingSummary: '两天前理解',
          ),
          {
            'role': 'user',
            'content': '刚刚问',
            'timestamp': recentUserTime.toIso8601String(),
          },
          _canonicalAssistantMessage(
            id: 'turn_recent',
            timestamp: recentAssistantTime.toIso8601String(),
            content: '刚刚答',
            understandingSummary: '刚刚理解',
          ),
        ],
      },
      'metadata': {},
    });

    final rounds = sm.recentDialogueRounds(
      'assistant',
      limit: 1,
      olderLimit: 1,
    );
    expect(rounds, hasLength(2));
    expect(rounds[0]['userQuery'], equals('刚刚问'));
    expect(rounds[1]['userQuery'], equals('两天前问'));

    final summary = sm.summarizeRecent(
      'assistant',
      roundsLimit: 1,
      roundsOlderLimit: 1,
    );
    expect(summary, contains('user: 两天前问'));
    expect(summary, contains('user: 刚刚问'));
    expect(
      summary.indexOf('user: 两天前问'),
      lessThan(summary.indexOf('user: 刚刚问')),
    );
  });

  test('Rule-5c: historyState 在 sessions.json metadata 中往返保持轻量字段', () async {
    final file = File('${tempDir.path}/sessions_history.json');
    final sm = AssistantSessionManager(storagePath: file.path);
    await sm.load();
    sm.updateSessionHistoryState(
      sessionId: 'assistant',
      historyState: const AssistantSessionHistoryState(
        sessionSummary: '上次已经确认了深圳天气适合出门。',
        completedSkillSummaries: <AssistantSkillHistorySummary>[
          AssistantSkillHistorySummary(
            skillId: 'weather',
            role: 'primary',
            summary: '已确认深圳天气适合出门。',
            status: 'complete',
            answerReady: true,
            acceptedEvidenceCount: 2,
          ),
        ],
        pendingSkillStates: <AssistantSkillPendingState>[
          AssistantSkillPendingState(
            skillId: 'calendar',
            role: 'supporting',
            summary: '待补充明天时间范围。',
            status: 'pending',
            nextAction: 'ask_user',
            missingSlots: <String>['date'],
          ),
        ],
        userPreferences: <PreferenceFact>[
          PreferenceFact(
            factId: 'pref_1',
            scope: 'session',
            key: 'city',
            value: '深圳',
            source: 'test',
            createdAt: '2026-04-09T10:00:00Z',
          ),
        ],
        lastAcceptedEvidenceSummary: 'weather: 深圳天气',
      ),
    );
    await sm.save();

    final reloaded = AssistantSessionManager(storagePath: file.path);
    await reloaded.load();
    final historyState = reloaded.historyStateOf('assistant');

    expect(historyState.sessionSummary, '上次已经确认了深圳天气适合出门。');
    expect(historyState.completedSkillSummaries, hasLength(1));
    expect(historyState.pendingSkillStates, hasLength(1));
    expect(historyState.userPreferences, hasLength(1));
    expect(historyState.lastAcceptedEvidenceSummary, contains('weather'));
  });

  test('Rule-6: root-level 旧历史格式不再兼容，load() 后直接清空', () async {
    final sm = await _loadFrom(tempDir, {
      'assistant': [
        {'role': 'user', 'content': '问题'},
        {'role': 'assistant', 'content': '老格式的回复内容'},
      ],
    });

    expect(sm.sessions, isEmpty);
    final stored = await _readStoredPayload(tempDir);
    expect(stored['version'], equals(assistantHistoryStorageVersion));
    expect(stored['sessions'], isEmpty);
  });

  test('Rule-2b: load() 会从 assistant sourceQuery 修复缺失用户消息', () async {
    final sm = await _loadFrom(tempDir, {
      'version': assistantHistoryStorageVersion,
      'activeSessionId': 'assistant',
      'sessions': {
        'assistant': [
          _canonicalAssistantMessage(
            sourceQuery: '今天A股走势怎样',
            timestamp: '10:30',
          ),
        ],
      },
      'metadata': {},
    });

    final messages = sm.sessions['assistant'] ?? const <Map<String, dynamic>>[];
    expect(messages, hasLength(2));
    expect(messages.first['role'], equals('user'));
    expect(messages.first['content'], equals('今天A股走势怎样'));
    expect(messages.last['role'], equals('assistant'));

    final stored = await _readStoredPayload(tempDir);
    final storedSessions = (stored['sessions'] as Map).cast<String, dynamic>();
    final storedMessages = (storedSessions['assistant'] as List)
        .cast<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
    expect(storedMessages.first['role'], equals('user'));
    expect(storedMessages.first['content'], equals('今天A股走势怎样'));
  });

  test('Rule-7: load() with missing file does not throw', () async {
    final sm = AssistantSessionManager(
      storagePath: '${tempDir.path}/nonexistent.json',
    );
    await expectLater(sm.load(), completes);
    expect(sm.getOrCreateSession('assistant').isEmpty, isTrue);
  });

  test('Rule-8: load() with invalid json clears file safely', () async {
    final file = File('${tempDir.path}/sessions_corrupted.json');
    await file.writeAsBytes(const <int>[0xff, 0xfe, 0xfd, 0x00]);

    final sm = AssistantSessionManager(storagePath: file.path);
    await expectLater(sm.load(), completes);
    expect(sm.getOrCreateSession('assistant').isEmpty, isTrue);

    await file.writeAsString('{not valid json');
    await expectLater(sm.load(), completes);
    expect(sm.getOrCreateSession('assistant').isEmpty, isTrue);
  });
}
