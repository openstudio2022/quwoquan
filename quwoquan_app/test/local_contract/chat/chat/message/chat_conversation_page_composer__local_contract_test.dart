import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_send_outbox.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import '../../../../support/cloud_services/user_typed_facet_test_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_composer_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('趣聊页使用微信式 composer：空态显示 emoji 和更多，输入后切发送', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            mutualRelationshipCapabilityRepository(),
          ),
          voiceQueuedSenderProvider.overrideWithValue(
            (_, _) async => VoiceSendStatus.completed,
          ),
        ],
        child: MaterialApp(
          home: ChatConversationPage(
            conversationId: 'fixture_conv_group',
            onBack: _noop,
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(TestKeys.chatInputVoiceToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputEmojiToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputMoreButton), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, '新的会话输入');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byKey(TestKeys.chatInputEmojiToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputMoreButton), findsNothing);
    expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);
  });
}

void _noop() {}
