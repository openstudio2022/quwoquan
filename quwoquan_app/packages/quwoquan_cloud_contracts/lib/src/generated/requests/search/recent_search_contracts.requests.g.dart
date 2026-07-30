// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../search/recent_search_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class ClearRecentSearchesCommand {
  ClearRecentSearchesCommand({
    String? scope,
  }) : scope = _normalizeGeneratedOptionalText(scope) {
  }

  final String? scope;
}

final class DeleteRecentSearchCommand {
  DeleteRecentSearchCommand({
    required String entryId,
  }) : entryId = entryId.trim() {
    if (this.entryId.isEmpty) {
      throw ArgumentError.value(this.entryId, "entryId", 'must not be blank');
    }
  }

  final String entryId;
}

final class ListRecentSearchesQuery {
  ListRecentSearchesQuery({
    String? scope,
  }) : scope = _normalizeGeneratedOptionalText(scope) {
  }

  final String? scope;
}

final class UpsertRecentSearchCommand {
  UpsertRecentSearchCommand({
    required String query,
    required String scope,
    String? facet,
  }) : query = query.trim(),
       scope = scope.trim(),
       facet = _normalizeGeneratedOptionalText(facet) {
    if (this.query.isEmpty) {
      throw ArgumentError.value(this.query, "query", 'must not be blank');
    }
    if (this.scope.isEmpty) {
      throw ArgumentError.value(this.scope, "scope", 'must not be blank');
    }
  }

  final String query;
  final String scope;
  final String? facet;
}

CloudOperationRequestPayload encodeSearchRecentSearchStateClearRecentSearchesGeneratedRequest(ClearRecentSearchesCommand request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.scope != null) "scope": request.scope!,
    },
  );
}

CloudOperationRequestPayload encodeSearchRecentSearchStateDeleteRecentSearchGeneratedRequest(DeleteRecentSearchCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "entryId": request.entryId,
    },
  );
}

CloudOperationRequestPayload encodeSearchRecentSearchStateListRecentSearchesGeneratedRequest(ListRecentSearchesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.scope != null) "scope": request.scope!,
    },
  );
}

CloudOperationRequestPayload encodeSearchRecentSearchStateUpsertRecentSearchGeneratedRequest(UpsertRecentSearchCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "query": request.query,
      "scope": request.scope,
      if (request.facet != null) "facet": request.facet!,
    },
  );
}

