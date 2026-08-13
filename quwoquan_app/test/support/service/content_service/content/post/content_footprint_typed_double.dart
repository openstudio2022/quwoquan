import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/footprint_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class FootprintTestEntry {
  const FootprintTestEntry({required this.type, required this.entry});

  final String type;
  final FootprintEntry entry;
}

/// 只读取调用 suite 显式交入的足迹对象。
final class InMemoryFootprintRepository implements FootprintRepository {
  InMemoryFootprintRepository({required Iterable<FootprintTestEntry> entries})
    : _entries = List<FootprintTestEntry>.unmodifiable(entries);

  final List<FootprintTestEntry> _entries;

  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = ContentFootprintQuery.defaultLimit,
  }) async {
    final normalizedType = type?.trim().toLowerCase() ?? '';
    final filtered = _entries
        .where((item) => normalizedType.isEmpty || item.type == normalizedType)
        .map((item) => item.entry)
        .toList(growable: false);
    final offset = int.tryParse(cursor?.trim() ?? '') ?? 0;
    final safeOffset = offset.clamp(0, filtered.length);
    final safeLimit = limit <= 0 ? filtered.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, filtered.length);
    return CursorPage<FootprintEntry>(
      items: filtered.sublist(safeOffset, end),
      nextCursor: end < filtered.length ? '$end' : null,
    );
  }
}
