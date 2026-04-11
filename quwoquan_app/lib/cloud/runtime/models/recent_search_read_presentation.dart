import 'package:quwoquan_app/core/models/search_models.dart';

/// 最近搜索条目的只读 UI 投影（与 `RecentSearchEntryView` 字段 1:1，便于后续挂 metadata projection）。
class RecentSearchReadPresentation {
  const RecentSearchReadPresentation({
    required this.entryId,
    required this.displayQuery,
    required this.scopeWire,
    this.facet,
    required this.updatedAt,
  });

  final String entryId;
  final String displayQuery;
  final String scopeWire;
  final String? facet;
  final DateTime updatedAt;

  factory RecentSearchReadPresentation.fromEntry(RecentSearchEntryView entry) {
    return RecentSearchReadPresentation(
      entryId: entry.entryId,
      displayQuery: entry.query,
      scopeWire: entry.scope.wireValue,
      facet: entry.facet,
      updatedAt: entry.updatedAt,
    );
  }
}
