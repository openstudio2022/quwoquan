// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/report_queries.dart';

final class ContentMyReportsQuery {
  const ContentMyReportsQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit;

  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeContentReportListMyReportsGeneratedRequest(ContentMyReportsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

