import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

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
    this.arguments = const <String, dynamic>{},
  });

  final String url;
  final int? maxChars;
  final Map<String, dynamic> arguments;

  factory RetrievalFetchRequest.fromToolArguments(Map<String, dynamic> arguments) {
    final rawMaxChars = arguments['maxChars'];
    return RetrievalFetchRequest(
      url: (arguments['url'] as String?)?.trim() ?? '',
      maxChars: rawMaxChars is num ? rawMaxChars.toInt() : null,
      arguments: Map<String, dynamic>.from(arguments),
    );
  }

  Map<String, dynamic> toToolArguments() => <String, dynamic>{
        ...arguments,
        'url': url,
        if (maxChars != null) 'maxChars': maxChars,
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
  final Map<String, dynamic>? data;
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

class RetrievalFetchResult {
  const RetrievalFetchResult({
    required this.success,
    required this.message,
    this.data,
    this.errorCode = AssistantErrorCode.none,
    this.degraded = false,
  });

  final bool success;
  final String message;
  final Map<String, dynamic>? data;
  final AssistantErrorCode errorCode;
  final bool degraded;

  factory RetrievalFetchResult.fromToolResult(AssistantToolResult result) {
    return RetrievalFetchResult(
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
