// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../notification/incoming_call_delivery_contracts.dart';

final class AckIncomingCallPresentationCommand {
  AckIncomingCallPresentationCommand({
    required String deliveryKey,
  }) : deliveryKey = deliveryKey.trim() {
    if (this.deliveryKey.isEmpty) {
      throw ArgumentError.value(this.deliveryKey, "deliveryKey", 'must not be blank');
    }
  }

  final String deliveryKey;
}

CloudOperationRequestPayload encodeNotificationNotificationDeliveryJobAckIncomingCallPresentationGeneratedRequest(AckIncomingCallPresentationCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "deliveryKey": request.deliveryKey,
    },
  );
}

