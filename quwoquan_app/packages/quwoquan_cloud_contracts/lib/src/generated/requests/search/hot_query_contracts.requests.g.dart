// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../search/hot_query_contracts.dart';

final class ListHotQueriesQuery {
  ListHotQueriesQuery({
    int limit = 10,
  }) : limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 20) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 20");
    }
  }

  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "limit": this.limit,
  };
}

CloudOperationRequestPayload encodeSearchSearchRequestFactListHotQueriesGeneratedRequest(ListHotQueriesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
    },
  );
}

