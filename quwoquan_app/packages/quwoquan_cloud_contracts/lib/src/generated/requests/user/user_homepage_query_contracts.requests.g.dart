// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/user_homepage_query_contracts.dart';

final class GetUserHomepageBundleQuery {
  const GetUserHomepageBundleQuery({
    required String personaId,
  }) : personaId = personaId;

  final String personaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
  };
}

CloudOperationRequestPayload encodeUserUserAccountGetUserHomepageBundleGeneratedRequest(GetUserHomepageBundleQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
  );
}

