import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

const _testPersonaContext = ActivePersonaContextViewData(
  personaId: 'fixture_persona_daily',
  ownerUserId: 'fixture_user_current',
  subjectType: 'person',
  displayName: '测试用户',
  avatarUrl: '',
  isPrimary: true,
);

void main() {
  // 本地会话搜索索引是真实 SQLite 投影，不是替身；VM 单测用 FFI 提供真实实现。
  setUpAll(ensureSqfliteFfiInitialized);

  testWidgets('进入会话后 realtime fixture 推送新消息并更新可见列表', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          // 被测行为是 realtime 事件如何进入可见消息列表；会话与身份只作为前置输入，
          // 用对象级 typed double 提供，App↔Cloud 出站边界保持封死。
          ...sealedCloudBoundaryOverrides(),
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => _testPersonaContext,
          ),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => _testPersonaContext,
          ),
        ],
        child: const MaterialApp(home: _RealtimeMessageJourney()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('Fixture Realtime 新消息：咖啡馆门口见。'), findsOneWidget);
  });
}

class _RealtimeMessageJourney extends ConsumerStatefulWidget {
  const _RealtimeMessageJourney();

  @override
  ConsumerState<_RealtimeMessageJourney> createState() =>
      _RealtimeMessageJourneyState();
}

class _RealtimeMessageJourneyState
    extends ConsumerState<_RealtimeMessageJourney> {
  late FixtureRealtimeConnectionDelegate _delegate;

  @override
  void initState() {
    super.initState();
    _delegate = FixtureRealtimeConnectionDelegate(
      read: ref.read,
      invalidate: ref.invalidate,
    );
    _delegate.onAppForeground();
    _delegate.onEnterConversation('conv_001');
  }

  @override
  void dispose() {
    _delegate.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatMessageProvider('conv_001'));
    return ListView(
      children: [
        for (final message in state.messages)
          Text(message.content ?? '', key: ValueKey<String>(message.id)),
      ],
    );
  }
}
