// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 0cc2789e805667e2728b001e7a199ec0c4bf9ff6e553b0bbf0098808429cea88

part of '../../../tag/tag_operation_contracts.g.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

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

void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}

String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}

int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class ListTagChildrenQuery {
  ListTagChildrenQuery({required String parentTagRef, required int limit})
    : parentTagRef = parentTagRef.trim(),
      limit = limit {
    if (this.parentTagRef.isEmpty) {
      throw ArgumentError.value(
        this.parentTagRef,
        "parentTagRef",
        'must not be blank',
      );
    }
  }

  final String parentTagRef;
  final int limit;

  factory ListTagChildrenQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListTagChildrenQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "parentTagRef",
      "limit",
    }, path);
    return ListTagChildrenQuery(
      parentTagRef: _generatedRequestString(
        map["parentTagRef"],
        '$path.parentTagRef',
      ),
      limit: _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "parentTagRef": this.parentTagRef,
    "limit": this.limit,
  };
}

final class ReportTagFeedbackCommand {
  ReportTagFeedbackCommand({
    required String tagRef,
    required TagFeedbackAction action,
    String? context,
  }) : tagRef = tagRef.trim(),
       action = action,
       context = _normalizeGeneratedOptionalText(context) {
    if (this.tagRef.isEmpty) {
      throw ArgumentError.value(this.tagRef, "tagRef", 'must not be blank');
    }
  }

  final String tagRef;
  final TagFeedbackAction action;
  final String? context;

  factory ReportTagFeedbackCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ReportTagFeedbackCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "tagRef",
      "action",
      "context",
    }, path);
    return ReportTagFeedbackCommand(
      tagRef: _generatedRequestString(map["tagRef"], '$path.tagRef'),
      action: switch (map["action"]) {
        "click" => TagFeedbackAction.click,
        "ignore" => TagFeedbackAction.ignore,
        "correct" => TagFeedbackAction.correct,
        "dislike" => TagFeedbackAction.dislike,
        _ => throw FormatException(
          '$path.action' + ' has an invalid enum value',
        ),
      },
      context: map["context"] == null
          ? null
          : _generatedRequestString(map["context"], '$path.context'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tagRef": this.tagRef,
    "action": this.action.wireName,
    if (this.context != null) "context": this.context!,
  };
}

final class ResolveTagQuery {
  ResolveTagQuery({required String tagRef}) : tagRef = tagRef.trim() {
    if (this.tagRef.isEmpty) {
      throw ArgumentError.value(this.tagRef, "tagRef", 'must not be blank');
    }
  }

  final String tagRef;

  factory ResolveTagQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ResolveTagQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tagRef"}, path);
    return ResolveTagQuery(
      tagRef: _generatedRequestString(map["tagRef"], '$path.tagRef'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"tagRef": this.tagRef};
}

final class ValidateTagRefsQuery {
  ValidateTagRefsQuery({
    required String expectedTaxonomyReleaseId,
    required Iterable<String> tagRefs,
  }) : expectedTaxonomyReleaseId = expectedTaxonomyReleaseId.trim(),
       tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: false) {
    if (this.expectedTaxonomyReleaseId.isEmpty) {
      throw ArgumentError.value(
        this.expectedTaxonomyReleaseId,
        "expectedTaxonomyReleaseId",
        'must not be blank',
      );
    }
    if (this.tagRefs.isEmpty) {
      throw ArgumentError.value(this.tagRefs, "tagRefs", 'must not be blank');
    }
  }

  final String expectedTaxonomyReleaseId;
  final List<String> tagRefs;

  factory ValidateTagRefsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ValidateTagRefsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "expectedTaxonomyReleaseId",
      "tagRefs",
    }, path);
    return ValidateTagRefsQuery(
      expectedTaxonomyReleaseId: _generatedRequestString(
        map["expectedTaxonomyReleaseId"],
        '$path.expectedTaxonomyReleaseId',
      ),
      tagRefs: List<String>.unmodifiable(
        _generatedRequestList(
          map["tagRefs"],
          '$path.tagRefs',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.tagRefs' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "expectedTaxonomyReleaseId": this.expectedTaxonomyReleaseId,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
  };
}

CloudOperationRequestPayload
encodeTagTagFeedbackFactReportTagFeedbackGeneratedRequest(
  ReportTagFeedbackCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "tagRef": request.tagRef,
      "action": request.action.wireName,
      if (request.context != null) "context": request.context!,
    },
  );
}

CloudOperationRequestPayload
encodeTagTagNodeViewListTagChildrenGeneratedRequest(
  ListTagChildrenQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "parentTagRef": request.parentTagRef,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeTagTagNodeViewResolveTagGeneratedRequest(
  ResolveTagQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{"tagRef": request.tagRef},
  );
}

CloudOperationRequestPayload
encodeTagTagNodeViewValidateTagRefsGeneratedRequest(
  ValidateTagRefsQuery request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "expectedTaxonomyReleaseId": request.expectedTaxonomyReleaseId,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
    },
  );
}
