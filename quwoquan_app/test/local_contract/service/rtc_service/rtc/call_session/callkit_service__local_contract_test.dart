// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-004
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_callkit_incoming/entities/call_event.dart';
import 'package:quwoquan_app/runtime/platform/callkit_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('CallKit event stream 不可用时安全降级，不抛全局 FlutterError', (
    tester,
  ) async {
    final service = CallKitService(
      eventStream: Stream<CallEvent?>.error(
        MissingPluginException('flutter_callkit_incoming_events'),
      ),
    );
    addTearDown(service.dispose);

    service.startListening();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1));

    expect(service.nativeEventStreamAvailable, isFalse);
    expect(tester.takeException(), isNull);
  });
}
