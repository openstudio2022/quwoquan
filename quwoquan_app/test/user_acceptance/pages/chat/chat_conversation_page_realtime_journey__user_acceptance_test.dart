import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_offline_queue.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_realtime_journey_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('会话页进入后 mock realtime 追加新消息', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_MockModeNotifier.new),
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            MockRelationshipCapabilityRepository(),
          ),
          voiceQueuedSenderProvider.overrideWithValue(
            (_, _) async => VoiceSendStatus.completed,
          ),
        ],
        child: MaterialApp(
          navigatorObservers: <NavigatorObserver>[chatRouteObserver],
          home: ChatConversationPage(conversationId: 'conv_001', onBack: _noop),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    final beforeCount =
        tester.container().read(chatMessageProvider('conv_001')).messages.length;

    await tester.pump(const Duration(milliseconds: 400));

    final afterMessages =
        tester.container().read(chatMessageProvider('conv_001')).messages;
    expect(afterMessages.length, greaterThan(beforeCount));
    expect(
      afterMessages.any(
        (message) =>
            message.content?.contains('Fixture Realtime 新消息：咖啡馆门口见。') ??
            false,
      ),
      isTrue,
    );

    tester.container()
        .read(realtimeConnectionManagerProvider.notifier)
        .onAppBackground();
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

final class _MockModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

void _noop() {}
