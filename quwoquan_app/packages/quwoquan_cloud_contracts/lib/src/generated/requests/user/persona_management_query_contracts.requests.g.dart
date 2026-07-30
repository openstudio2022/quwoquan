// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/persona_management_query_contracts.dart';

final class GetActivePersonaContextQuery {
  const GetActivePersonaContextQuery();
}

final class GetPersonaLifecycleGuardQuery {
  const GetPersonaLifecycleGuardQuery({
    required String personaId,
  }) : personaId = personaId;

  final String personaId;
}

final class GetPersonaManagementSummaryQuery {
  const GetPersonaManagementSummaryQuery();
}

final class ListPersonasQuery {
  const ListPersonasQuery();
}

CloudOperationRequestPayload encodeUserUserAccountGetActivePersonaContextGeneratedRequest(GetActivePersonaContextQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserAccountGetPersonaLifecycleGuardGeneratedRequest(GetPersonaLifecycleGuardQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeUserUserAccountGetPersonaManagementSummaryGeneratedRequest(GetPersonaManagementSummaryQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserAccountListPersonasGeneratedRequest(ListPersonasQuery request) {
  return CloudOperationRequestPayload(
  );
}

