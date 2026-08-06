// spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';

final class _RecordingAcknowledger
    implements IncomingCallPresentationAcknowledger {
  IncomingCallPresentationReceipt? receipt;

  @override
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt) async {
    this.receipt = receipt;
  }
}

void main() {
  test('公开 ACK 端口保留 deliveryKey、来源与真实展示时刻', () async {
    final writer = _RecordingAcknowledger();
    final presentedAt = DateTime.utc(2026, 8, 5, 9, 30);

    await writer.acknowledge(
      IncomingCallPresentationReceipt(
        callId: 'call-notification-contract',
        deliveryKey: 'delivery-notification-contract',
        source: IncomingCallPresentationSource.nativePush,
        presentedAt: presentedAt,
      ),
    );

    expect(writer.receipt?.callId, 'call-notification-contract');
    expect(writer.receipt?.deliveryKey, 'delivery-notification-contract');
    expect(writer.receipt?.source.wireName, 'native_push');
    expect(writer.receipt?.presentedAt, presentedAt);
  });
}
