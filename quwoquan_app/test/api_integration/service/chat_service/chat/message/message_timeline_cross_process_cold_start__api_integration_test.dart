// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/spec.md#sit-001.t1
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/spec.md#sit-001.t2
//
// 冷启动跨进程证据（api_integration，真实 SQLite + 独立 OS 进程）：
// 独立 `flutter test` 子进程（writer）向共享磁盘路径写入 timeline 后退出；
// 主进程冷启动水合同一路径，断言按 seq 有序完整读回（sit-001.t1）。
// 恢复网络增量收敛在同库上叠加 sync 补齐消息，断言无重复且已读位置不回退
// （sit-001.t2 的持久层收敛面；notifier 收敛链见
// message_timeline_persistence_paging__reliability__local_contract_test.dart）。
@Timeout(Duration(minutes: 6))
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';

import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

const _scope = ChatMessageTimelineScope(
  ownerUserId: 'user_cross_process',
  personaId: 'persona_cross_process',
  subjectType: 'owner',
  contextVersion: '1',
);

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  test('独立 writer 进程写入后主进程冷启动水合且增量收敛无重复', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'timeline_cross_process_',
    );
    addTearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });
    final databasePath = '${tempDir.path}/chat_search.db';

    // 独立 OS 进程写入真实 SQLite（同一 LocalChatSearchStore 真相源）。
    final writer = await Process.run('flutter', [
      'test',
      'test/api_integration/service/chat_service/chat/message/'
          'message_timeline_cold_start_writer__api_integration_test.dart',
      '--dart-define=COLD_START_DB_PATH=$databasePath',
    ], workingDirectory: Directory.current.path);
    expect(
      writer.exitCode,
      0,
      reason: 'writer 进程必须成功写入：${writer.stdout}\n${writer.stderr}',
    );
    expect(
      File(databasePath).existsSync(),
      isTrue,
      reason: 'writer 进程必须产出真实磁盘数据库文件',
    );

    // 主进程冷启动：全新 store 打开同一路径水合（sit-001.t1）。
    final coldStore = LocalChatSearchStore(
      databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
      databasePath: databasePath,
    );
    addTearDown(coldStore.close);
    await coldStore.ensureReady();
    final restored = await coldStore.readMessages(
      scope: _scope,
      conversationId: 'conv_cross_process',
    );
    expect(restored, hasLength(6), reason: '跨进程写入的 timeline 必须完整可读');
    expect(
      restored.map((message) => message.seq).toList(),
      [1, 2, 3, 4, 5, 6],
      reason: '冷启动水合必须按 seq 升序',
    );
    expect(restored.first.content, '跨进程冷启动消息 1');

    // 恢复网络后的增量收敛：sync 补齐 7..8 并重放已有 5..6（模拟重叠窗口），
    // 断言无重复条目且已有序列不回退（sit-001.t2 持久层语义）。
    await coldStore.writeMessages(
      scope: _scope,
      messages: [
        for (var seq = 5; seq <= 8; seq++)
          ChatMessageViewData(
            id: 'cross_process_$seq',
            conversationId: 'conv_cross_process',
            seq: seq,
            clientMsgId: 'client_cross_$seq',
            senderId: 'persona_peer',
            senderName: '跨进程同行者',
            type: 'text',
            content: '跨进程冷启动消息 $seq',
            status: 'sent',
            timestamp: DateTime.utc(2026, 8, 14, 2, seq),
          ),
      ],
    );
    final converged = await coldStore.readMessages(
      scope: _scope,
      conversationId: 'conv_cross_process',
    );
    expect(
      converged.map((message) => message.seq).toList(),
      [1, 2, 3, 4, 5, 6, 7, 8],
      reason: '增量收敛不得产生重复条目，也不得回退已有序列',
    );
    expect(
      converged.map((message) => message.id).toSet().length,
      converged.length,
      reason: '重叠窗口重放必须按主键幂等',
    );
  });
}
