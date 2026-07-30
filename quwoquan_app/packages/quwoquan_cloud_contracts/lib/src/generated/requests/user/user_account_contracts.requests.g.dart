// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/user_account_contracts.dart';

final class CloseAccountCommand {
  const CloseAccountCommand({
    String? clientRequestId,
  }) : clientRequestId = clientRequestId;

  final String? clientRequestId;
}

CloudOperationRequestPayload encodeUserUserAccountCloseAccountGeneratedRequest(CloseAccountCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.clientRequestId != null) "clientRequestId": request.clientRequestId!,
    },
  );
}

