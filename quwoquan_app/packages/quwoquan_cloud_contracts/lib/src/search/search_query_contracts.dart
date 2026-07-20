import '../operation_cancellation.dart';
import '../operation_request_payload.dart';

enum CanonicalSearchMode {
  suggest('suggest'),
  result('result');

  const CanonicalSearchMode(this.wireValue);
  final String wireValue;
}

final class CanonicalSearchQuery {
  CanonicalSearchQuery({
    required String query,
    this.mode = CanonicalSearchMode.result,
    Iterable<String> objectTypes = const <String>[],
    this.limit = 20,
  }) : query = _requiredText(query, 'query'),
       objectTypes = List<String>.unmodifiable(
         objectTypes.map((item) => item.trim()).where((item) => item.isNotEmpty),
       ) {
    if (limit <= 0 || limit > 50) {
      throw ArgumentError.value(limit, 'limit', 'must be between 1 and 50');
    }
  }

  final String query;
  final CanonicalSearchMode mode;
  final List<String> objectTypes;
  final int limit;
}

final class CanonicalSearchIntersectionReason {
  const CanonicalSearchIntersectionReason({
    this.primaryText = '',
    this.intersectionId = '',
    this.dimension = '',
    this.intersectionClass = '',
    this.sourceRef = '',
  });

  final String primaryText;
  final String intersectionId;
  final String dimension;
  final String intersectionClass;
  final String sourceRef;
}

/// content.post 命中的 typed slice。它属于 canonical Search hit，不是独立业务对象。
final class CanonicalSearchContentHit {
  const CanonicalSearchContentHit({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.summary,
    this.coverUrl,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.categoryId,
    this.subCategory,
    this.likeCount = 0,
    this.highlightText,
    this.matchedField,
    this.publishedAt,
    this.connectionState = 'unconnected',
    this.intersectionReason,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? summary;
  final String? coverUrl;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? categoryId;
  final String? subCategory;
  final int likeCount;
  final String? highlightText;
  final String? matchedField;
  final DateTime? publishedAt;
  final String connectionState;
  final CanonicalSearchIntersectionReason? intersectionReason;
}

final class CanonicalSearchHit {
  CanonicalSearchHit({
    required this.target,
    required this.objectId,
    required this.title,
    this.snippet,
    this.score = 0,
    this.matchedField,
    this.rankReasons = const <String>[],
    this.rankPosition,
    this.coverWidth,
    this.coverHeight,
    this.connectionState = 'unconnected',
    this.intersectionReason,
    this.content,
    Map<String, Object?> payload = const <String, Object?>{},
  }) : payload = Map<String, Object?>.unmodifiable(payload);

  final String target;
  final String objectId;
  final String title;
  final String? snippet;
  final double score;
  final String? matchedField;
  final List<String> rankReasons;
  final int? rankPosition;
  final double? coverWidth;
  final double? coverHeight;
  final String connectionState;
  final CanonicalSearchIntersectionReason? intersectionReason;
  final CanonicalSearchContentHit? content;

  /// 非 content 对象的 transport payload。content 消费方必须读取 [content]，
  /// 禁止把该 Map 回转为 Post DTO。
  final Map<String, Object?> payload;
}

final class CanonicalSearchDegradeSignal {
  const CanonicalSearchDegradeSignal({
    required this.code,
    required this.message,
    this.objectType,
  });

  final String code;
  final String message;
  final String? objectType;
}

final class CanonicalSearchResult {
  CanonicalSearchResult({
    required Iterable<CanonicalSearchHit> hits,
    required this.requestId,
    required this.rankingVersion,
    this.experimentBucket,
    Iterable<String> relatedTerms = const <String>[],
    Iterable<CanonicalSearchDegradeSignal> degradeSignals =
        const <CanonicalSearchDegradeSignal>[],
  }) : hits = List<CanonicalSearchHit>.unmodifiable(hits),
       relatedTerms = List<String>.unmodifiable(relatedTerms),
       degradeSignals = List<CanonicalSearchDegradeSignal>.unmodifiable(
         degradeSignals,
       );

  final List<CanonicalSearchHit> hits;
  final String requestId;
  final String rankingVersion;
  final String? experimentBucket;
  final List<String> relatedTerms;
  final List<CanonicalSearchDegradeSignal> degradeSignals;
}

abstract interface class CanonicalSearchQueryFacet {
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}

CloudOperationRequestPayload encodeCanonicalSearchQuery(
  CanonicalSearchQuery query,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'query': query.query,
    'mode': query.mode.wireValue,
    'objectTypes': query.objectTypes,
    'limit': query.limit,
  },
);

CanonicalSearchResult decodeCanonicalSearchResult(Object? value) {
  final root = _object(value, 'CanonicalSearchResult');
  final hits = _list(root['hits'], 'CanonicalSearchResult.hits')
      .map(_decodeHit)
      .toList(growable: false);
  return CanonicalSearchResult(
    hits: hits,
    requestId: _requiredText(root['requestId'], 'requestId'),
    rankingVersion: _requiredText(root['rankingVersion'], 'rankingVersion'),
    experimentBucket: _optionalText(root['experimentBucket']),
    relatedTerms: _stringList(root['relatedTerms'], 'relatedTerms'),
    degradeSignals: _list(
      root['degradeSignals'],
      'degradeSignals',
      optional: true,
    ).map(_decodeDegradeSignal),
  );
}

CanonicalSearchHit _decodeHit(Object? value) {
  final hit = _object(value, 'CanonicalSearchHit');
  final target = _requiredText(hit['target'], 'target');
  final objectId = _requiredText(hit['objectId'], 'objectId');
  final title = _requiredText(hit['title'], 'title');
  final payload = _optionalObject(hit['payload'], 'payload');
  final intersectionReason = _decodeIntersectionReason(
    hit['intersectionReason'],
  );
  final evidence = _list(hit['evidence'], 'evidence', optional: true);
  final matchedField = evidence.isEmpty
      ? null
      : _optionalText(_object(evidence.first, 'evidence item')['field']);
  final contentType = switch (target) {
    'photo' => 'image',
    'video' => 'video',
    'article' => 'article',
    _ => null,
  };
  final connectionState =
      _optionalText(hit['connectionState']) ?? 'unconnected';
  return CanonicalSearchHit(
    target: target,
    objectId: objectId,
    title: title,
    snippet: _optionalText(hit['snippet']),
    score: _optionalDouble(hit['score']) ?? 0,
    matchedField: matchedField,
    rankReasons: _list(
      hit['rankReasons'],
      'rankReasons',
      optional: true,
    ).map((reason) {
      final map = _object(reason, 'rank reason');
  return _optionalText(map['label']) ?? '';
    }).where((label) => label.isNotEmpty).toList(growable: false),
    rankPosition: _optionalInt(hit['rankPosition']),
    coverWidth: _positiveDouble(hit['coverWidth'] ?? payload['coverWidth']),
    coverHeight: _positiveDouble(hit['coverHeight'] ?? payload['coverHeight']),
    connectionState: connectionState,
    intersectionReason: intersectionReason,
    content: contentType == null
        ? null
        : CanonicalSearchContentHit(
            postId: objectId,
            contentType: contentType,
            contentIdentity: _optionalText(payload['contentIdentity']),
            title: title,
            summary: _optionalText(hit['snippet']),
            coverUrl: _optionalText(payload['coverUrl']),
            authorId: _optionalText(payload['authorId']),
            authorDisplayName: _optionalText(payload['authorDisplayName']),
            authorAvatarUrl: _optionalText(payload['authorAvatarUrl']),
            categoryId: _optionalText(payload['categoryId']),
            subCategory: _optionalText(payload['subCategory']),
            likeCount: _optionalInt(payload['likeCount']) ?? 0,
            highlightText: _optionalText(hit['snippet']),
            matchedField: matchedField,
            publishedAt: _optionalDateTime(payload['publishedAt']),
            connectionState: connectionState,
            intersectionReason: intersectionReason,
          ),
    payload: payload,
  );
}

CanonicalSearchIntersectionReason? _decodeIntersectionReason(Object? value) {
  if (value == null) {
    return null;
  }
  final reason = _object(value, 'intersectionReason');
  return CanonicalSearchIntersectionReason(
    primaryText: _optionalText(reason['primaryText']) ?? '',
    intersectionId: _optionalText(reason['intersectionId']) ?? '',
    dimension: _optionalText(reason['dimension']) ?? '',
    intersectionClass: _optionalText(reason['class']) ?? '',
    sourceRef: _optionalText(reason['sourceRef']) ?? '',
  );
}

CanonicalSearchDegradeSignal _decodeDegradeSignal(Object? value) {
  final signal = _object(value, 'degradeSignal');
  return CanonicalSearchDegradeSignal(
        code: _optionalText(signal['code']) ?? '',
        message: _optionalText(signal['message']) ?? '',
        objectType: _optionalText(signal['objectType']),
  );
}

Map<String, Object?> _object(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

Map<String, Object?> _optionalObject(Object? value, String context) {
  if (value == null) {
    return const <String, Object?>{};
  }
  return _object(value, context);
}

List<Object?> _list(
  Object? value,
  String context, {
  bool optional = false,
}) {
  if (value == null && optional) {
    return const <Object?>[];
  }
  if (value is! List) {
    throw FormatException('$context must be a list');
  }
  return value.cast<Object?>();
}

List<String> _stringList(Object? value, String context) {
  if (value == null) {
    return const <String>[];
  }
  return _list(value, context)
      .map((item) {
        if (item is! String) {
          throw FormatException('$context must contain strings');
        }
        return item.trim();
      })
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String _requiredText(Object? value, String name) {
  final text = _optionalText(value);
  if (text == null) {
    throw FormatException('$name must be a non-empty string');
  }
  return text;
}

String? _optionalText(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw const FormatException('Expected a string value');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int? _optionalInt(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value.trim());
  }
  throw const FormatException('Expected an integer value');
}

double? _optionalDouble(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value.trim());
  }
  throw const FormatException('Expected a numeric value');
}

double? _positiveDouble(Object? value) {
  final parsed = _optionalDouble(value);
  return parsed != null && parsed > 0 ? parsed : null;
}

DateTime? _optionalDateTime(Object? value) {
  final text = _optionalText(value);
  if (text == null) {
    return null;
  }
  final parsed = DateTime.tryParse(text);
  if (parsed == null) {
    throw const FormatException('Expected an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}
