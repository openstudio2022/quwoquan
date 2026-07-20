import 'package:quwoquan_app/application/rtc/call_session/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef IncomingCallPresentationInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteIncomingCallPresentationAcknowledger
    implements IncomingCallPresentationAcknowledger {
  const RemoteIncomingCallPresentationAcknowledger({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final IncomingCallPresentationInvocationContextFactory invocationContext;

  @override
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt) async {
    await client.notificationNotificationDeliveryJobAckIncomingCallPresentation(
      AckIncomingCallPresentationCommand(deliveryKey: receipt.deliveryKey),
      context: invocationContext(
        NotificationRequestPageIds.ackIncomingCallPresentation,
      ),
    );
  }
}
