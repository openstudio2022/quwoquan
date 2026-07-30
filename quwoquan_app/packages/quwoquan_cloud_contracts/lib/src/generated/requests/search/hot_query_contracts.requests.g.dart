// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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
}

CloudOperationRequestPayload encodeSearchSearchQueryListHotQueriesGeneratedRequest(ListHotQueriesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
    },
  );
}

