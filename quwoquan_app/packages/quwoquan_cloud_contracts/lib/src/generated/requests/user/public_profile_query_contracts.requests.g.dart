// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/public_profile_query_contracts.dart';

final class GetMeProfileQuery {
  const GetMeProfileQuery();
}

final class GetPersonaProfileQuery {
  const GetPersonaProfileQuery({
    required String personaId,
  }) : personaId = personaId;

  final String personaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class GetProfileQrCardQuery {
  const GetProfileQrCardQuery();
}

final class ResolveProfileQrTokenQuery {
  const ResolveProfileQrTokenQuery({
    required String qr,
    String? handle,
  }) : qr = qr,
       handle = handle;

  final String qr;
  final String? handle;

  Map<String, Object?> toJson() => <String, Object?>{
    "qr": this.qr,
    if (this.handle?.isNotEmpty == true) "handle": this.handle!,
  };
}

final class SearchSocialRelationsQuery {
  const SearchSocialRelationsQuery({
    required String query,
    String? cursor,
    int limit = 20,
  }) : query = query,
       cursor = cursor,
       limit = limit;

  final String query;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "query": this.query,
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

CloudOperationRequestPayload encodeUserUserAccountGetMeProfileGeneratedRequest(GetMeProfileQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserAccountGetPersonaProfileGeneratedRequest(GetPersonaProfileQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeUserUserAccountGetProfileQrCardGeneratedRequest(GetProfileQrCardQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserUserAccountResolveProfileQrTokenGeneratedRequest(ResolveProfileQrTokenQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "qr": request.qr,
      if (request.handle?.isNotEmpty == true) "handle": request.handle!,
    },
  );
}

CloudOperationRequestPayload encodeUserUserAccountSearchSocialRelationsGeneratedRequest(SearchSocialRelationsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "query": request.query,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

