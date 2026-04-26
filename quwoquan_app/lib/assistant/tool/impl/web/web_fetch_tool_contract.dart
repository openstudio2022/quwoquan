import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

const String webFetchToolContractVersion = 'web_fetch_v1';

class WebFetchToolArgs {
  const WebFetchToolArgs({
    required this.url,
    this.maxChars,
    this.searchPlanId = '',
    this.dimension = '',
  });

  final String url;
  final int? maxChars;
  final String searchPlanId;
  final String dimension;

  factory WebFetchToolArgs.fromAssistantArguments(
    AssistantToolArguments arguments,
  ) {
    return WebFetchToolArgs(
      url: arguments.stringField('url') ?? '',
      maxChars: arguments.intField('maxChars'),
      searchPlanId: arguments.stringField('searchPlanId') ?? '',
      dimension: arguments.stringField('dimension') ?? '',
    );
  }

  RetrievalFetchRequest toRetrievalFetchRequest() {
    return RetrievalFetchRequest(
      url: url,
      maxChars: maxChars,
      searchPlanId: searchPlanId,
      dimension: dimension,
    );
  }

  AssistantToolArguments toAssistantArguments() {
    return AssistantToolArguments(<String, Object?>{
      'url': url,
      if (maxChars != null) 'maxChars': maxChars,
      if (searchPlanId.trim().isNotEmpty) 'searchPlanId': searchPlanId.trim(),
      if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
    });
  }
}

class WebFetchReference {
  const WebFetchReference({
    this.url = '',
    this.title = '',
    this.source = '',
    this.sourceHost = '',
    this.snippet = '',
    this.sourceTier = '',
    this.searchPlanId = '',
    this.dimension = '',
    this.retrievedAt = '',
  });

  final String url;
  final String title;
  final String source;
  final String sourceHost;
  final String snippet;
  final String sourceTier;
  final String searchPlanId;
  final String dimension;
  final String retrievedAt;

  factory WebFetchReference.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return WebFetchReference(
      url: payload.stringField('url') ?? '',
      title: payload.stringField('title') ?? '',
      source: payload.stringField('source') ?? '',
      sourceHost: payload.stringField('sourceHost') ?? '',
      snippet: payload.stringField('snippet') ?? '',
      sourceTier: payload.stringField('sourceTier') ?? '',
      searchPlanId: payload.stringField('searchPlanId') ?? '',
      dimension: payload.stringField('dimension') ?? '',
      retrievedAt: payload.stringField('retrievedAt') ?? '',
    );
  }

  factory WebFetchReference.fromRetrievalReference(
    RetrievalFetchReference value,
  ) {
    return WebFetchReference(
      url: value.url,
      title: value.title,
      source: value.source,
      sourceHost: value.sourceHost,
      snippet: value.snippet,
      sourceTier: value.sourceTier,
      searchPlanId: value.searchPlanId,
      dimension: value.dimension,
      retrievedAt: value.retrievedAt,
    );
  }

  static List<WebFetchReference> listFromJson(Object? raw) {
    if (raw is! List) {
      return const <WebFetchReference>[];
    }
    return raw
        .map(WebFetchReference.fromJson)
        .where(
          (item) => item.url.trim().isNotEmpty || item.title.trim().isNotEmpty,
        )
        .toList(growable: false);
  }

  RetrievalFetchReference toRetrievalReference() {
    return RetrievalFetchReference(
      url: url,
      title: title,
      source: source,
      sourceHost: sourceHost,
      snippet: snippet,
      sourceTier: sourceTier,
      searchPlanId: searchPlanId,
      dimension: dimension,
      retrievedAt: retrievedAt,
    );
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      if (url.trim().isNotEmpty) 'url': url.trim(),
      if (title.trim().isNotEmpty) 'title': title.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
      if (sourceHost.trim().isNotEmpty) 'sourceHost': sourceHost.trim(),
      if (snippet.trim().isNotEmpty) 'snippet': snippet.trim(),
      if (sourceTier.trim().isNotEmpty) 'sourceTier': sourceTier.trim(),
      if (searchPlanId.trim().isNotEmpty) 'searchPlanId': searchPlanId.trim(),
      if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
      if (retrievedAt.trim().isNotEmpty) 'retrievedAt': retrievedAt.trim(),
    };
  }
}

class WebFetchToolSuccessPayload {
  const WebFetchToolSuccessPayload({
    this.url = '',
    this.title = '',
    this.source = '',
    this.content = '',
    this.summary = '',
    this.charCount,
    this.truncated,
    this.contentType = '',
    this.sourceHost = '',
    this.sourceTier = '',
    this.searchPlanId = '',
    this.dimension = '',
    this.references = const <WebFetchReference>[],
  });

  final String url;
  final String title;
  final String source;
  final String content;
  final String summary;
  final int? charCount;
  final bool? truncated;
  final String contentType;
  final String sourceHost;
  final String sourceTier;
  final String searchPlanId;
  final String dimension;
  final List<WebFetchReference> references;

  factory WebFetchToolSuccessPayload.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return WebFetchToolSuccessPayload(
      url: payload.stringField('url') ?? '',
      title: payload.stringField('title') ?? '',
      source: payload.stringField('source') ?? '',
      content: payload['content']?.toString().trim() ?? '',
      summary: payload.stringField('summary') ?? '',
      charCount: payload.intField('charCount'),
      truncated: payload.boolField('truncated'),
      contentType: payload.stringField('contentType') ?? '',
      sourceHost: payload.stringField('sourceHost') ?? '',
      sourceTier: payload.stringField('sourceTier') ?? '',
      searchPlanId: payload.stringField('searchPlanId') ?? '',
      dimension: payload.stringField('dimension') ?? '',
      references: WebFetchReference.listFromJson(payload['references']),
    );
  }

  factory WebFetchToolSuccessPayload.fromRetrievalPayload(
    RetrievalFetchResultPayload payload,
  ) {
    return WebFetchToolSuccessPayload(
      url: payload.url,
      title: payload.title,
      source: payload.source,
      content: payload.content,
      summary: payload.summary,
      charCount: payload.charCount,
      truncated: payload.truncated,
      contentType: payload.contentType,
      sourceHost: payload.sourceHost,
      sourceTier: payload.sourceTier,
      searchPlanId: payload.searchPlanId,
      dimension: payload.dimension,
      references: payload.references
          .map(WebFetchReference.fromRetrievalReference)
          .toList(growable: false),
    );
  }

  WebFetchToolSuccessPayload copyWith({
    String? url,
    String? title,
    String? source,
    String? content,
    String? summary,
    int? charCount,
    bool? truncated,
    String? contentType,
    String? sourceHost,
    String? sourceTier,
    String? searchPlanId,
    String? dimension,
    List<WebFetchReference>? references,
  }) {
    return WebFetchToolSuccessPayload(
      url: url ?? this.url,
      title: title ?? this.title,
      source: source ?? this.source,
      content: content ?? this.content,
      summary: summary ?? this.summary,
      charCount: charCount ?? this.charCount,
      truncated: truncated ?? this.truncated,
      contentType: contentType ?? this.contentType,
      sourceHost: sourceHost ?? this.sourceHost,
      sourceTier: sourceTier ?? this.sourceTier,
      searchPlanId: searchPlanId ?? this.searchPlanId,
      dimension: dimension ?? this.dimension,
      references: references ?? this.references,
    );
  }

  AssistantToolResultData toResultData() {
    return AssistantToolResultData(<String, Object?>{
      'contractVersion': webFetchToolContractVersion,
      if (url.trim().isNotEmpty) 'url': url.trim(),
      if (title.trim().isNotEmpty) 'title': title.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
      if (content.trim().isNotEmpty) 'content': content.trim(),
      if (summary.trim().isNotEmpty) 'summary': summary.trim(),
      if (charCount != null) 'charCount': charCount,
      if (truncated != null) 'truncated': truncated,
      if (contentType.trim().isNotEmpty) 'contentType': contentType.trim(),
      if (sourceHost.trim().isNotEmpty) 'sourceHost': sourceHost.trim(),
      if (sourceTier.trim().isNotEmpty) 'sourceTier': sourceTier.trim(),
      if (searchPlanId.trim().isNotEmpty) 'searchPlanId': searchPlanId.trim(),
      if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
      'references': references
          .map((item) => item.toJson())
          .toList(growable: false),
    });
  }
}

class WebFetchFailurePayload {
  const WebFetchFailurePayload({
    this.statusCode,
    this.contentType = '',
    this.detail = '',
  });

  final int? statusCode;
  final String contentType;
  final String detail;

  AssistantToolResultData toResultData() {
    return AssistantToolResultData(<String, Object?>{
      'contractVersion': webFetchToolContractVersion,
      if (statusCode != null) 'statusCode': statusCode,
      if (contentType.trim().isNotEmpty) 'contentType': contentType.trim(),
      if (detail.trim().isNotEmpty) 'detail': detail.trim(),
    });
  }
}
