// spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// readiness_case: notification_delivery_job_ack_incoming_call_presentation_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/notification/notification_request_page_ids.g.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/adapters/incoming_call_presentation_remote.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class _RecordingAcknowledger
    implements NotificationDeliveryJobProcessCommandWriter {
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

  test(
    'production Remote 仅上送 canonical deliveryKey 并执行 typed decode',
    () async {
      final executor = _RecordingExecutor();
      final writer = RemoteIncomingCallPresentationAcknowledger(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'rtc.incoming-call',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
            deviceActorId: 'device-1',
          ),
        ),
      );

      await writer.acknowledge(
        IncomingCallPresentationReceipt(
          callId: 'call-1',
          deliveryKey: 'delivery-1',
          source: IncomingCallPresentationSource.nativePush,
          presentedAt: DateTime.utc(2026, 8, 8, 9, 30),
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds
            .notificationNotificationDeliveryJobAckIncomingCallPresentation,
      );
      expect(executor.operation?.method, 'POST');
      expect(
        executor.operation?.pathTemplate,
        '/notifications/incoming-calls/presentation:ack',
      );
      expect(
        executor.context?.clientPageId,
        NotificationRequestPageIds.ackIncomingCallPresentation,
      );
      expect(executor.context?.actor.deviceActorId, 'device-1');
      expect(executor.payload?.pathParameters, isEmpty);
      expect(executor.payload?.queryParameters, isEmpty);
      expect(executor.payload?.body, <String, Object?>{
        'deliveryKey': 'delivery-1',
      });
      expect(executor.payload?.body, isNot(contains('callId')));
      expect(executor.payload?.body, isNot(contains('source')));
      expect(executor.payload?.body, isNot(contains('presentedAt')));
      final decoded = executor.decodedResponse;
      expect(decoded, isA<AckIncomingCallPresentationResult>());
      expect(
        (decoded as AckIncomingCallPresentationResult).deliveryKey,
        'delivery-1',
      );
      expect(decoded.deviceId, 'device-1');
      expect(decoded.status, 'realtime_presented');
      expect(decoded.raced, isFalse);
    },
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? payload;
  Object? decodedResponse;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    payload = requestEncoder();
    final decoded = responseDecoder(<String, Object?>{
      'deliveryKey': 'delivery-1',
      'deviceId': 'device-1',
      'status': 'realtime_presented',
      'raced': false,
      'acknowledgedAt': '2026-08-08T09:30:01Z',
    });
    decodedResponse = decoded;
    return decoded;
  }
}
