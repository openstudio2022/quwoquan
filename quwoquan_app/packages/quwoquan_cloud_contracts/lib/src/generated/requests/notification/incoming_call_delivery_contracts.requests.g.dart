// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "deliveryKey": this.deliveryKey,
  };
}

CloudOperationRequestPayload encodeNotificationNotificationDeliveryJobAckIncomingCallPresentationGeneratedRequest(AckIncomingCallPresentationCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "deliveryKey": request.deliveryKey,
    },
  );
}

