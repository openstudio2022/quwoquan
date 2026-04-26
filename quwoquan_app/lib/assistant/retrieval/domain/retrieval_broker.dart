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

  List<RetrievalSearchPlan> get queryPlans => RetrievalSearchPlan.listFromJson(
    arguments['taskGraphSearchPlan'] ?? arguments['searchPlans'],
  );

  Map<String, dynamic> toToolArguments() => <String, dynamic>{
        ...arguments,
        'query': query,
        'count': count,
      };
}

class RetrievalSearchPlan {
  const RetrievalSearchPlan({
    this.id = '',
    this.label = '',
    this.dimension = '',
    required this.query,
    this.entityRefs = const <String>[],
    this.negativeKeywords = const <String>[],
    this.answerShape = '',
    this.freshnessNeed = '',
    this.timeScope = '',
    this.timeRangeStart = '',
    this.timeRangeEnd = '',
    this.timePoint = '',
    this.timezone = '',
  });

  final String id;
  final String label;
  final String dimension;
  final String query;
  final List<String> entityRefs;
  final List<String> negativeKeywords;
  final String answerShape;
  final String freshnessNeed;
  final String timeScope;
  final String timeRangeStart;
  final String timeRangeEnd;
  final String timePoint;
  final String timezone;

  factory RetrievalSearchPlan.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return RetrievalSearchPlan(
      id: payload.stringField('id') ?? '',
      label: payload.stringField('label') ?? '',
      dimension: payload.stringField('dimension') ?? '',
      query: payload.stringField('query') ?? '',
      entityRefs: payload.stringListField('entityRefs'),
      negativeKeywords: payload.stringListField('negativeKeywords'),
      answerShape: payload.stringField('answerShape') ?? '',
      freshnessNeed: payload.stringField('freshnessNeed') ?? '',
      timeScope: payload.stringField('timeScope') ?? '',
      timeRangeStart: payload.stringField('timeRangeStart') ?? '',
      timeRangeEnd: payload.stringField('timeRangeEnd') ?? '',
      timePoint: payload.stringField('timePoint') ?? '',
      timezone: payload.stringField('timezone') ?? '',
    );
  }

  static List<RetrievalSearchPlan> listFromJson(Object? raw) {
    if (raw is! List) {
      return const <RetrievalSearchPlan>[];
    }
    return raw
        .map(RetrievalSearchPlan.fromJson)
        .where((item) => item.query.trim().isNotEmpty)
        .toList(growable: false);
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      if (id.trim().isNotEmpty) 'id': id.trim(),
      if (label.trim().isNotEmpty) 'label': label.trim(),
      if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
      'query': query.trim(),
      if (entityRefs.isNotEmpty) 'entityRefs': entityRefs.toList(growable: false),
      if (negativeKeywords.isNotEmpty)
        'negativeKeywords': negativeKeywords.toList(growable: false),
      if (answerShape.trim().isNotEmpty) 'answerShape': answerShape.trim(),
      if (freshnessNeed.trim().isNotEmpty)
        'freshnessNeed': freshnessNeed.trim(),
      if (timeScope.trim().isNotEmpty) 'timeScope': timeScope.trim(),
      if (timeRangeStart.trim().isNotEmpty)
        'timeRangeStart': timeRangeStart.trim(),
      if (timeRangeEnd.trim().isNotEmpty) 'timeRangeEnd': timeRangeEnd.trim(),
      if (timePoint.trim().isNotEmpty) 'timePoint': timePoint.trim(),
      if (timezone.trim().isNotEmpty) 'timezone': timezone.trim(),
    };
  }

  List<String> dimensionLabels() {
    final normalizedDimension = dimension.trim();
    final normalizedLabel = label.trim();
    return <String>[
      if (normalizedDimension.isNotEmpty)
        normalizedDimension
      else if (normalizedLabel.isNotEmpty)
        normalizedLabel,
    ];
  }

  List<String> labels() {
    final normalized = label.trim();
    if (normalized.isEmpty) {
      return const <String>[];
    }
    return <String>[normalized];
  }
}

class RetrievalFetchRequest {
  const RetrievalFetchRequest({
    required this.url,
    this.maxChars,
    this.searchPlanId = '',
    this.dimension = '',
  });

  final String url;
  final int? maxChars;
  final String searchPlanId;
  final String dimension;

  factory RetrievalFetchRequest.fromToolArguments(Map<String, dynamic> arguments) {
    final rawMaxChars = arguments['maxChars'];
    return RetrievalFetchRequest(
      url: (arguments['url'] as String?)?.trim() ?? '',
      maxChars: rawMaxChars is num ? rawMaxChars.toInt() : null,
      searchPlanId: (arguments['searchPlanId'] as String?)?.trim() ?? '',
      dimension: (arguments['dimension'] as String?)?.trim() ?? '',
    );
  }

  Map<String, dynamic> toToolArguments() => <String, dynamic>{
        'url': url,
        if (maxChars != null) 'maxChars': maxChars,
        if (searchPlanId.trim().isNotEmpty)
          'searchPlanId': searchPlanId.trim(),
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

  factory RetrievalFetchReference.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return RetrievalFetchReference(
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
      if (searchPlanId.trim().isNotEmpty)
        'searchPlanId': searchPlanId.trim(),
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
    this.searchPlanId = '',
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
  final String searchPlanId;
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
      searchPlanId: payload.stringField('searchPlanId') ?? '',
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
    String? searchPlanId,
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
      searchPlanId: searchPlanId ?? this.searchPlanId,
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
        if (searchPlanId.trim().isNotEmpty)
          'searchPlanId': searchPlanId.trim(),
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
