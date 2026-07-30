import '../operation_request_payload.dart';
import 'report_commands.dart';
part '../generated/requests/content/report_queries.requests.g.dart';

/// 举报聚合对举报人公开的生命周期状态。
enum ContentReportStatus { pending, reviewing, resolved, dismissed }

/// 当前举报人私有可见的举报进度项。
final class ContentMyReportItem {
  const ContentMyReportItem({
    required this.id,
    required this.targetType,
    required this.targetId,
    required this.reason,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.description,
    this.resolvedAt,
  });

  final String id;
  final ContentReportTargetType targetType;
  final String targetId;
  final ContentReportReason reason;
  final String? description;
  final ContentReportStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;
}



final class ContentMyReportPage {
  ContentMyReportPage({
    required Iterable<ContentMyReportItem> items,
    this.nextCursor,
  }) : items = List<ContentMyReportItem>.unmodifiable(items);

  final List<ContentMyReportItem> items;
  final String? nextCursor;
}

abstract interface class ContentMyReportQueryFacet {
  Future<ContentMyReportPage> listMyReports(ContentMyReportsQuery query);
}



ContentMyReportPage decodeContentMyReportPage(Object? response) {
  final root = _expectObject(response, 'My reports response');
  final items = _expectList(root['items'], 'My reports response.items');
  return ContentMyReportPage(
    items: items.map(_decodeContentMyReportItem),
    nextCursor: _optionalText(root['nextCursor']),
  );
}

ContentMyReportItem _decodeContentMyReportItem(Object? rawItem) {
  final item = _expectObject(rawItem, 'My report item');
  return ContentMyReportItem(
    id: _requiredText(item['id'], 'id'),
    targetType: _enumByName(
      ContentReportTargetType.values,
      item['targetType'],
      'targetType',
    ),
    targetId: _requiredText(item['targetId'], 'targetId'),
    reason: _enumByName(ContentReportReason.values, item['reason'], 'reason'),
    description: _optionalText(item['description']),
    status: _enumByName(ContentReportStatus.values, item['status'], 'status'),
    createdAt: _requiredDateTime(item['createdAt'], 'createdAt'),
    updatedAt: _requiredDateTime(item['updatedAt'], 'updatedAt'),
    resolvedAt: _optionalDateTime(item['resolvedAt'], 'resolvedAt'),
  );
}

Map<String, Object?> _expectObject(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  return value.map<String, Object?>((key, item) {
    if (key is! String) {
      throw FormatException('$label contains a non-string key');
    }
    return MapEntry<String, Object?>(key, item);
  });
}

List<Object?> _expectList(Object? value, String label) {
  if (value is! List) {
    throw FormatException('$label must be an array');
  }
  return List<Object?>.from(value);
}

String _requiredText(Object? value, String field) {
  final normalized = _optionalText(value);
  if (normalized == null) {
    throw FormatException('$field must not be empty');
  }
  return normalized;
}

String? _optionalText(Object? value) {
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('expected string');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

DateTime _requiredDateTime(Object? value, String field) {
  final parsed = _optionalDateTime(value, field);
  if (parsed == null) {
    throw FormatException('$field must not be empty');
  }
  return parsed;
}

DateTime? _optionalDateTime(Object? value, String field) {
  if (value == null) return null;
  final raw = _requiredText(value, field);
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

T _enumByName<T extends Enum>(List<T> values, Object? value, String field) {
  final name = _requiredText(value, field);
  for (final candidate in values) {
    if (candidate.name == name) return candidate;
  }
  throw FormatException('$field has unsupported value: $name');
}
