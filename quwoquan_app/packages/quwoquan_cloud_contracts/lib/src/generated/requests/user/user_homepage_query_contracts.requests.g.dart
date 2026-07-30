// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/user_homepage_query_contracts.dart';

final class GetUserHomepageBundleQuery {
  const GetUserHomepageBundleQuery({
    required String personaId,
  }) : personaId = personaId;

  final String personaId;
}

CloudOperationRequestPayload encodeUserUserAccountGetUserHomepageBundleGeneratedRequest(GetUserHomepageBundleQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
  );
}

