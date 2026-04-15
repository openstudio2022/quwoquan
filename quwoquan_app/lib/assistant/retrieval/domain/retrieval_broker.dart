import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

abstract class RetrievalBroker {
  Future<RetrievalSearchResult> search(RetrievalSearchRequest request);

  Future<RetrievalFetchResult> fetch(RetrievalFetchRequest request);
}

class RetrievalSearchRequest {
  const RetrievalSearchRequest({
    required this.query,
    this.count = 5,
    this.arguments = const <String, dynamic>{},
  });

  final String query;
  final int count;
  final Map<String, dynamic> arguments;

  factory RetrievalSearchRequest.fromToolArguments(
    Map<String, dynamic> arguments,
  ) {
    final rawQuery = (arguments['query'] as String?)?.trim() ?? '';
    final rawCount = arguments['count'];
    return RetrievalSearchRequest(
      query: rawQuery,
      count: rawCount is num ? rawCount.toInt() : 5,
      arguments: Map<String, dynamic>.from(arguments),
    );
  }

  String get providerHint => (arguments['provider'] as String?)?.trim() ?? '';

  String get domainId {
    return ((arguments['domainId'] as String?)?.trim().isNotEmpty == true
            ? (arguments['domainId'] as String).trim()
            : (arguments['__domainId'] as String?)?.trim()) ??
        '';
  }

  String get sessionId => (arguments['__sessionId'] as String?)?.trim() ?? '';

  String get runId => (arguments['__runId'] as String?)?.trim() ?? '';

  String get traceId => (arguments['__traceId'] as String?)?.trim() ?? '';

  List<Map<String, dynamic>> get queryTasks =>
      (arguments['queryTasks'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];

  Map<String, dynamic> toToolArguments() => <String, dynamic>{
        ...arguments,
        'query': query,
        'count': count,
      };
}

class RetrievalFetchRequest {
  const RetrievalFetchRequest({
    required this.url,
    this.maxChars,
    this.queryTaskId = '',
    this.dimension = '',
  });

  final String url;
  final int? maxChars;
  final String queryTaskId;
  final String dimension;

  factory RetrievalFetchRequest.fromToolArguments(Map<String, dynamic> arguments) {
    final rawMaxChars = arguments['maxChars'];
    return RetrievalFetchRequest(
      url: (arguments['url'] as String?)?.trim() ?? '',
      maxChars: rawMaxChars is num ? rawMaxChars.toInt() : null,
      queryTaskId: (arguments['queryTaskId'] as String?)?.trim() ?? '',
      dimension: (arguments['dimension'] as String?)?.trim() ?? '',
    );
  }

  Map<String, dynamic> toToolArguments() => <String, dynamic>{
        'url': url,
        if (maxChars != null) 'maxChars': maxChars,
        if (queryTaskId.trim().isNotEmpty) 'queryTaskId': queryTaskId.trim(),
        if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
      };
}

class RetrievalSearchResult {
  const RetrievalSearchResult({
    required this.success,
    required this.message,
    this.data,
    this.errorCode = AssistantErrorCode.none,
    this.degraded = false,
  });

  final bool success;
  final String message;
  final AssistantToolResultData? data;
  final AssistantErrorCode errorCode;
  final bool degraded;

  factory RetrievalSearchResult.fromToolResult(AssistantToolResult result) {
    return RetrievalSearchResult(
      success: result.success,
      message: result.message,
      data: result.data,
      errorCode: result.errorCode,
      degraded: result.degraded,
    );
  }

  AssistantToolResult toToolResult() => AssistantToolResult(
        success: success,
        message: message,
        data: data,
        errorCode: errorCode,
        degraded: degraded,
      );
}

/// Typed read surface for `web_search` entries in [RetrievalSearchResult.data]
/// (broker → tool boundary; keeps downstream off raw `data[...]` indexing).
class BrokerWebSearchResultDataView {
  BrokerWebSearchResultDataView(Map<String, dynamic> data)
    : _data = Map<String, dynamic>.from(data);

  final Map<String, dynamic> _data;

  /// Raw map for mutation paths that still merge keys into tool payloads.
  Map<String, dynamic> get raw => _data;

  String valueOf(String key) =>
      (_data[key] as Object?)?.toString().trim() ?? '';

  List<Map<String, dynamic>> get embeddedReferences =>
      (_data['references'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];

  String get summaryOrSnippet {
    final summary = valueOf('summary');
    if (summary.isNotEmpty) return summary;
    return valueOf('snippet');
  }
}

class RetrievalFetchReference {
  const RetrievalFetchReference({
    this.url = '',
    this.title = '',
    this.source = '',
    this.sourceHost = '',
    this.snippet = '',
    this.sourceTier = '',
    this.queryTaskId = '',
    this.dimension = '',
    this.retrievedAt = '',
  });

  final String url;
  final String title;
  final String source;
  final String sourceHost;
  final String snippet;
  final String sourceTier;
  final String queryTaskId;
  final String dimension;
  final String retrievedAt;

  factory RetrievalFetchReference.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return RetrievalFetchReference(
      url: payload.stringField('url') ?? '',
      title: payload.stringField('title') ?? '',
      source: payload.stringField('source') ?? '',
      sourceHost: payload.stringField('sourceHost') ?? '',
      snippet: payload.stringField('snippet') ?? '',
      sourceTier: payload.stringField('sourceTier') ?? '',
      queryTaskId: payload.stringField('queryTaskId') ?? '',
      dimension: payload.stringField('dimension') ?? '',
      retrievedAt: payload.stringField('retrievedAt') ?? '',
    );
  }

  static List<RetrievalFetchReference> listFromJson(Object? raw) {
    if (raw is! List) {
      return const <RetrievalFetchReference>[];
    }
    return raw
        .map(RetrievalFetchReference.fromJson)
        .where(
          (item) =>
              item.url.trim().isNotEmpty || item.title.trim().isNotEmpty,
        )
        .toList(growable: false);
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      if (url.trim().isNotEmpty) 'url': url.trim(),
      if (title.trim().isNotEmpty) 'title': title.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
      if (sourceHost.trim().isNotEmpty) 'sourceHost': sourceHost.trim(),
      if (snippet.trim().isNotEmpty) 'snippet': snippet.trim(),
      if (sourceTier.trim().isNotEmpty) 'sourceTier': sourceTier.trim(),
      if (queryTaskId.trim().isNotEmpty) 'queryTaskId': queryTaskId.trim(),
      if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
      if (retrievedAt.trim().isNotEmpty) 'retrievedAt': retrievedAt.trim(),
    };
  }
}

class RetrievalFetchResultPayload {
  const RetrievalFetchResultPayload({
    this.url = '',
    this.title = '',
    this.source = '',
    this.sourceHost = '',
    this.content = '',
    this.summary = '',
    this.sourceTier = '',
    this.queryTaskId = '',
    this.dimension = '',
    this.contentType = '',
    this.charCount,
    this.truncated,
    this.references = const <RetrievalFetchReference>[],
  });

  final String url;
  final String title;
  final String source;
  final String sourceHost;
  final String content;
  final String summary;
  final String sourceTier;
  final String queryTaskId;
  final String dimension;
  final String contentType;
  final int? charCount;
  final bool? truncated;
  final List<RetrievalFetchReference> references;

  factory RetrievalFetchResultPayload.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return RetrievalFetchResultPayload(
      url: payload.stringField('url') ?? '',
      title: payload.stringField('title') ?? '',
      source: payload.stringField('source') ?? '',
      sourceHost: payload.stringField('sourceHost') ?? '',
      content: payload['content']?.toString().trim() ?? '',
      summary: payload.stringField('summary') ?? '',
      sourceTier: payload.stringField('sourceTier') ?? '',
      queryTaskId: payload.stringField('queryTaskId') ?? '',
      dimension: payload.stringField('dimension') ?? '',
      contentType: payload.stringField('contentType') ?? '',
      charCount: payload.intField('charCount'),
      truncated: payload.boolField('truncated'),
      references: RetrievalFetchReference.listFromJson(payload['references']),
    );
  }

  bool get isEmpty =>
      url.trim().isEmpty &&
      title.trim().isEmpty &&
      source.trim().isEmpty &&
      content.trim().isEmpty &&
      summary.trim().isEmpty &&
      references.isEmpty;

  RetrievalFetchResultPayload copyWith({
    String? url,
    String? title,
    String? source,
    String? sourceHost,
    String? content,
    String? summary,
    String? sourceTier,
    String? queryTaskId,
    String? dimension,
    String? contentType,
    int? charCount,
    bool? truncated,
    List<RetrievalFetchReference>? references,
  }) {
    return RetrievalFetchResultPayload(
      url: url ?? this.url,
      title: title ?? this.title,
      source: source ?? this.source,
      sourceHost: sourceHost ?? this.sourceHost,
      content: content ?? this.content,
      summary: summary ?? this.summary,
      sourceTier: sourceTier ?? this.sourceTier,
      queryTaskId: queryTaskId ?? this.queryTaskId,
      dimension: dimension ?? this.dimension,
      contentType: contentType ?? this.contentType,
      charCount: charCount ?? this.charCount,
      truncated: truncated ?? this.truncated,
      references: references ?? this.references,
    );
  }

  AssistantToolResultData toResultData() {
    return AssistantToolResultData(
      <String, Object?>{
        if (url.trim().isNotEmpty) 'url': url.trim(),
        if (title.trim().isNotEmpty) 'title': title.trim(),
        if (source.trim().isNotEmpty) 'source': source.trim(),
        if (sourceHost.trim().isNotEmpty) 'sourceHost': sourceHost.trim(),
        if (content.trim().isNotEmpty) 'content': content.trim(),
        if (summary.trim().isNotEmpty) 'summary': summary.trim(),
        if (sourceTier.trim().isNotEmpty) 'sourceTier': sourceTier.trim(),
        if (queryTaskId.trim().isNotEmpty) 'queryTaskId': queryTaskId.trim(),
        if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
        if (contentType.trim().isNotEmpty) 'contentType': contentType.trim(),
        if (charCount != null) 'charCount': charCount,
        if (truncated != null) 'truncated': truncated,
        if (references.isNotEmpty)
          'references': references
              .map((item) => item.toJson())
              .toList(growable: false),
      },
    );
  }
}

class RetrievalFetchResult {
  const RetrievalFetchResult({
    required this.success,
    required this.message,
    this.payload,
    this.data,
    this.errorCode = AssistantErrorCode.none,
    this.degraded = false,
  });

  final bool success;
  final String message;
  final RetrievalFetchResultPayload? payload;
  final AssistantToolResultData? data;
  final AssistantErrorCode errorCode;
  final bool degraded;

  factory RetrievalFetchResult.fromToolResult(AssistantToolResult result) {
    return RetrievalFetchResult(
      success: result.success,
      message: result.message,
      payload: (() {
        final payload = RetrievalFetchResultPayload.fromJson(result.data);
        return payload.isEmpty ? null : payload;
      })(),
      data: result.data,
      errorCode: result.errorCode,
      degraded: result.degraded,
    );
  }

  RetrievalFetchResultPayload? get payloadOrNull {
    final current = payload;
    if (current != null && !current.isEmpty) {
      return current;
    }
    final parsed = RetrievalFetchResultPayload.fromJson(data);
    return parsed.isEmpty ? null : parsed;
  }

  RetrievalFetchResult copyWith({
    bool? success,
    String? message,
    RetrievalFetchResultPayload? payload,
    AssistantToolResultData? data,
    AssistantErrorCode? errorCode,
    bool? degraded,
  }) {
    return RetrievalFetchResult(
      success: success ?? this.success,
      message: message ?? this.message,
      payload: payload ?? this.payload,
      data: data ?? this.data,
      errorCode: errorCode ?? this.errorCode,
      degraded: degraded ?? this.degraded,
    );
  }

  AssistantToolResult toToolResult() => AssistantToolResult(
        success: success,
        message: message,
        data: payloadOrNull?.toResultData() ?? data,
        errorCode: errorCode,
        degraded: degraded,
      );
}
