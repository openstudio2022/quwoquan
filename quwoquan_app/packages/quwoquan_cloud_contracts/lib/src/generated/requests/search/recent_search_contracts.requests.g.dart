// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.scope != null) "scope": this.scope!,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "entryId": this.entryId,
  };
}

final class ListRecentSearchesQuery {
  ListRecentSearchesQuery({
    String? scope,
  }) : scope = _normalizeGeneratedOptionalText(scope) {
  }

  final String? scope;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.scope != null) "scope": this.scope!,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "query": this.query,
    "scope": this.scope,
    if (this.facet != null) "facet": this.facet!,
  };
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

