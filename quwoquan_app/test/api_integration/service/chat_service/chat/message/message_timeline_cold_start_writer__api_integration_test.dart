// 冷启动跨进程证据的 writer 侧入口：由
// message_timeline_cross_process_cold_start__api_integration_test.dart 以独立
// `flutter test` 进程拉起，向 `--dart-define=COLD_START_DB_PATH` 指定的真实
// SQLite 路径写入 timeline 后退出。直接运行（未注入路径）时空转通过，
// 不产生第二套断言真相源。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';

import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

const _databasePath = String.fromEnvironment('COLD_START_DB_PATH');

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  test('writer 进程向注入路径写入真实 SQLite timeline', () async {
    if (_databasePath.isEmpty) {
      markTestSkipped('仅由跨进程冷启动主测试注入 COLD_START_DB_PATH 时执行');
      return;
    }
    const scope = ChatMessageTimelineScope(
      ownerUserId: 'user_cross_process',
      personaId: 'persona_cross_process',
      subjectType: 'owner',
      contextVersion: '1',
    );
    final store = LocalChatSearchStore(
      databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
      databasePath: _databasePath,
    );
    await store.ensureReady();
    await store.writeMessages(
      scope: scope,
      messages: [
        for (var seq = 1; seq <= 6; seq++)
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
    await store.close();
  });
}
