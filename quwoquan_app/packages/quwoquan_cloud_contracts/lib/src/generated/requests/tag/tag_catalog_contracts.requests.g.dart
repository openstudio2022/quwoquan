// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../tag/tag_catalog_contracts.dart';

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class ListTagChildrenQuery {
  ListTagChildrenQuery({
    required String parentTagRef,
    int limit = TagApiDefaults.childrenLimit,
  }) : parentTagRef = parentTagRef.trim(),
       limit = limit {
    if (this.parentTagRef.isEmpty) {
      throw ArgumentError.value(this.parentTagRef, "parentTagRef", 'must not be blank');
    }
  }

  final String parentTagRef;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "parentTagRef": this.parentTagRef,
    "limit": this.limit,
  };
}

final class ResolveTagQuery {
  ResolveTagQuery({
    required String tagRef,
  }) : tagRef = tagRef.trim() {
    if (this.tagRef.isEmpty) {
      throw ArgumentError.value(this.tagRef, "tagRef", 'must not be blank');
    }
  }

  final String tagRef;

  Map<String, Object?> toJson() => <String, Object?>{
    "tagRef": this.tagRef,
  };
}

final class ValidateTagRefsQuery {
  ValidateTagRefsQuery({
    required String expectedTaxonomyReleaseId,
    required Iterable<String> tagRefs,
  }) : expectedTaxonomyReleaseId = expectedTaxonomyReleaseId.trim(),
       tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: false) {
    if (this.expectedTaxonomyReleaseId.isEmpty) {
      throw ArgumentError.value(this.expectedTaxonomyReleaseId, "expectedTaxonomyReleaseId", 'must not be blank');
    }
    if (this.tagRefs.isEmpty) {
      throw ArgumentError.value(this.tagRefs, "tagRefs", 'must not be blank');
    }
  }

  final String expectedTaxonomyReleaseId;
  final List<String> tagRefs;

  Map<String, Object?> toJson() => <String, Object?>{
    "expectedTaxonomyReleaseId": this.expectedTaxonomyReleaseId,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeTagTagNodeViewListTagChildrenGeneratedRequest(ListTagChildrenQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "parentTagRef": request.parentTagRef,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeTagTagNodeViewResolveTagGeneratedRequest(ResolveTagQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "tagRef": request.tagRef,
    },
  );
}

CloudOperationRequestPayload encodeTagTagNodeViewValidateTagRefsGeneratedRequest(ValidateTagRefsQuery request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "expectedTaxonomyReleaseId": request.expectedTaxonomyReleaseId,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
    },
  );
}

