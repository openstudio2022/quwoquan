import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';

import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

void main() {
  testWidgets('进入会话后 realtime fixture 推送新消息并更新可见列表', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: _RealtimeMessageJourney())),
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
