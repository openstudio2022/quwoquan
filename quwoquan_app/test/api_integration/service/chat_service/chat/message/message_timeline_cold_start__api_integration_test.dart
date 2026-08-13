// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-timeline-local-persistence/spec.md#gwt-001
//
// 时间线冷启动读回（api_integration，真实 SQLite 磁盘文件）：
// 第一个 store 实例写入消息 timeline 后关闭；第二个实例（模拟应用冷启动的
// 新进程）打开同一数据库文件读回，消息按 seq 升序完整可读，且不同 persona
// scope 的 timeline 相互隔离。
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';

import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

ChatMessageViewData _timelineMessage(int seq) {
  return ChatMessageViewData(
    id: 'cold_start_$seq',
    conversationId: 'conv_cold_start',
    seq: seq,
    clientMsgId: 'client_cold_$seq',
    senderId: 'persona_writer',
    senderName: '观星同行者',
    type: 'text',
    content: '冷启动消息 $seq',
    status: 'sent',
    timestamp: DateTime.utc(2026, 8, 13, 7, seq),
  );
}

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  test('时间线写入后由新 store 实例冷启动读回并保持 scope 隔离', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'timeline_cold_start_',
    );
    addTearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });
    final databasePath = '${tempDir.path}/chat_search.db';
    const scope = ChatMessageTimelineScope(
      ownerUserId: 'user_writer',
      personaId: 'persona_writer',
      subjectType: 'owner',
      contextVersion: '1',
    );
    const otherScope = ChatMessageTimelineScope(
      ownerUserId: 'user_other',
      personaId: 'persona_other',
      subjectType: 'owner',
      contextVersion: '1',
    );

    // 第一个进程：写入并关闭。
    final writerStore = LocalChatSearchStore(
      databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
      databasePath: databasePath,
    );
    await writerStore.ensureReady();
    await writerStore.writeMessages(
      scope: scope,
      messages: [for (var seq = 1; seq <= 5; seq++) _timelineMessage(seq)],
    );
    await writerStore.close();

    // 第二个进程（冷启动）：新实例打开同一磁盘文件读回。
    final coldStartStore = LocalChatSearchStore(
      databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
      databasePath: databasePath,
    );
    addTearDown(coldStartStore.close);
    await coldStartStore.ensureReady();

    final restored = await coldStartStore.readMessages(
      scope: scope,
      conversationId: 'conv_cold_start',
    );
    expect(restored, hasLength(5));
    expect(
      restored.map((message) => message.seq).toList(),
      [1, 2, 3, 4, 5],
      reason: '冷启动读回必须按 seq 升序完整恢复',
    );
    expect(restored.first.content, '冷启动消息 1');
    expect(restored.last.senderName, '观星同行者');

    // 分页游标语义在冷启动后依然成立。
    final olderPage = await coldStartStore.readMessages(
      scope: scope,
      conversationId: 'conv_cold_start',
      beforeSeq: 4,
      limit: 2,
    );
    expect(olderPage.map((message) => message.seq).toList(), [2, 3]);

    // 其他 persona scope 在同一数据库文件中读不到该 timeline。
    final isolated = await coldStartStore.readMessages(
      scope: otherScope,
      conversationId: 'conv_cold_start',
    );
    expect(isolated, isEmpty, reason: 'persona scope 必须隔离本地 timeline');
  });
}
