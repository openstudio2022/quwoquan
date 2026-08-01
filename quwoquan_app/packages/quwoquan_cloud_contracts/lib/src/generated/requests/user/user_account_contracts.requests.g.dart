// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/user_account_contracts.dart';

final class CloseAccountCommand {
  const CloseAccountCommand({
    String? clientRequestId,
  }) : clientRequestId = clientRequestId;

  final String? clientRequestId;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.clientRequestId != null) "clientRequestId": this.clientRequestId!,
  };
}

CloudOperationRequestPayload encodeUserUserAccountCloseAccountGeneratedRequest(CloseAccountCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.clientRequestId != null) "clientRequestId": request.clientRequestId!,
    },
  );
}

