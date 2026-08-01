// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/persona_management_query_contracts.dart';

final class GetActivePersonaContextQuery {
  const GetActivePersonaContextQuery();
}

final class GetPersonaLifecycleGuardQuery {
  const GetPersonaLifecycleGuardQuery({
    required String personaId,
  }) : personaId = personaId;

  final String personaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
  };
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

